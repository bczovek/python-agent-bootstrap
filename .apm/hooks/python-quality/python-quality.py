#!/usr/bin/env python3
"""PostToolUse hook: runs ruff format, ruff check, and mypy on any Python file
created or edited by the agent. Receives the JSON payload on stdin and writes
a JSON response to stdout if issues are found.

Works with Copilot CLI, VS Code Copilot, and Claude-family harnesses. Lines
marked "COPILOT-ONLY" or "HARNESS-SPECIFIC" are compatibility shims.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

# HARNESS-SPECIFIC: tool names differ per harness.
_WRITE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "create",  # COPILOT-ONLY: Copilot CLI
        "edit",  # COPILOT-ONLY: Copilot CLI
        "apply_patch",  # COPILOT-ONLY: Copilot CLI / VS Code
        "create_file",  # COPILOT-ONLY: VS Code
        "replace_string_in_file",  # COPILOT-ONLY: VS Code
        "multi_replace_string_in_file",  # COPILOT-ONLY: VS Code
        "Write",  # Claude Code
        "Edit",  # Claude Code
        "MultiEdit",  # Claude Code
    }
)
_PATH_KEYS: Final[tuple[str, ...]] = ("path", "file_path", "filePath")

_DEFAULT_LOG_LEVEL: Final[str] = "INFO"
# Harness-neutral location; the original used ~/.copilot/hooks/debug (COPILOT-ONLY).
_LOG_FILE_PATH: Final[Path] = (
    Path.home() / ".apm" / "hooks" / "debug" / "python-quality.log"
)


def _resolve_log_level() -> int:
    raw_level = os.getenv("LOG_LEVEL", _DEFAULT_LOG_LEVEL).strip().upper()
    return getattr(logging, raw_level, logging.INFO)


def _build_logger(log_level: int) -> logging.Logger:
    _LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger: logging.Logger = logging.getLogger("python-quality")
    logger.handlers.clear()
    logger.setLevel(log_level)
    handler = logging.FileHandler(_LOG_FILE_PATH, mode="a", encoding="utf-8")
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def _last_line(output: str) -> str:
    lines: list[str] = [line for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _payload_str(payload: dict[str, object], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return value if isinstance(value, str) else default


def _run(cmd: list[str]) -> tuple[int, str]:
    if shutil.which(cmd[0]) is None:
        return 127, f"{cmd[0]} is not installed or not on PATH"
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    return result.returncode, (result.stdout + result.stderr).strip()


def _tool_name(payload: dict[str, object]) -> str:
    # HARNESS-SPECIFIC: snake_case (Claude, VS Code) vs camelCase (Copilot CLI).
    return _payload_str(payload, "tool_name") or _payload_str(payload, "toolName")


def _tool_input(payload: dict[str, object]) -> object:
    # HARNESS-SPECIFIC: Claude/VS Code send an object; Copilot CLI sends a JSON string.
    return payload.get("tool_input", payload.get("toolArgs"))


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _paths_from_dict(data: dict[str, object]) -> list[str]:
    found: list[object] = [data.get(key) for key in _PATH_KEYS]
    replacements = data.get("replacements")
    if isinstance(replacements, list):
        for item in replacements:
            found.extend(_as_dict(item).get(key) for key in _PATH_KEYS)
    return [p for p in found if isinstance(p, str) and p]


def _paths_from_patch(tool_input: object) -> list[str]:
    text = (
        tool_input
        if isinstance(tool_input, str)
        else _as_dict(tool_input).get("input")
    )
    if not isinstance(text, str):
        return []
    return list(
        re.findall(r"^\*{3} (?:Add|Update|Delete) File: (.+)$", text, re.MULTILINE)
    )


def _raw_paths_from_input(tool_name: str, tool_input: object) -> list[str]:
    """Extract raw file path strings from the harness tool input."""
    if tool_name == "apply_patch":
        return _paths_from_patch(tool_input)
    return _paths_from_dict(_as_dict(tool_input))


def _resolve_file_paths(payload: dict[str, object]) -> list[Path]:
    """Return resolved, deduplicated Python file paths to check from the payload."""
    tool_name = _tool_name(payload)
    tool_input = _tool_input(payload)
    cwd = _payload_str(payload, "cwd", ".")
    seen: set[Path] = set()
    result: list[Path] = []
    for p_str in _raw_paths_from_input(tool_name, tool_input):
        if not p_str.endswith(".py"):
            continue
        p = Path(p_str) if Path(p_str).is_absolute() else Path(cwd) / p_str
        p = p.resolve()
        if p.exists() and p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _find_ruff_config(file_path: Path, workspace_root: Path) -> Path | None:
    """Walk up from file_path to workspace_root looking for a ruff config file."""
    search = file_path.parent.resolve()
    stop = workspace_root.resolve()
    while True:
        for name in ("ruff.toml", ".ruff.toml"):
            if (search / name).exists():
                return search / name
        pyproject = search / "pyproject.toml"
        if pyproject.exists() and "[tool.ruff" in pyproject.read_text(encoding="utf-8"):
            return pyproject
        if search in (stop, search.parent):
            return None
        search = search.parent


def _find_mypy_config(file_path: Path, workspace_root: Path) -> Path | None:
    """Walk up from file_path to workspace_root looking for a mypy config file."""
    search = file_path.parent.resolve()
    stop = workspace_root.resolve()
    while True:
        for name in ("mypy.ini", ".mypy.ini"):
            if (search / name).exists():
                return search / name
        pyproject = search / "pyproject.toml"
        if pyproject.exists() and "[tool.mypy]" in pyproject.read_text(
            encoding="utf-8"
        ):
            return pyproject
        if search in (stop, search.parent):
            return None
        search = search.parent


def _run_step(
    step_name: str,
    cmd: list[str],
    logger: logging.Logger,
) -> tuple[int, str]:
    exit_code, output = _run(cmd)
    if exit_code == 127:
        logger.error("%s: %s", step_name, output)
    else:
        logger.info("%s (exit=%s): %s", step_name, exit_code, _last_line(output))
    logger.debug("%s command: %s", step_name, " ".join(cmd))
    logger.debug("%s full output:\n%s", step_name, output)
    return exit_code, output


def _run_checks(
    file_path: Path, workspace_root: Path, logger: logging.Logger
) -> list[str]:
    # Fallback config ships next to this script in the deployed hook bundle.
    fallback_config = Path(__file__).parent / "pyproject.toml"

    ruff_config = _find_ruff_config(file_path, workspace_root)
    ruff_config_args = [] if ruff_config else ["--config", str(fallback_config)]

    mypy_config = _find_mypy_config(file_path, workspace_root)
    mypy_config_file = mypy_config if mypy_config else fallback_config

    issues: list[str] = []
    logger.info("Checking file: %s", file_path)

    _run_step(
        "ruff format",
        ["ruff", "format", *ruff_config_args, str(file_path)],
        logger,
    )

    ruff_exit, ruff_out = _run_step(
        "ruff check",
        ["ruff", "check", *ruff_config_args, str(file_path)],
        logger,
    )
    if ruff_exit != 0:
        issues.append(f"ruff:\n{ruff_out}")

    mypy_exit, mypy_out = _run_step(
        "mypy",
        [
            "mypy",
            "--config-file",
            str(mypy_config_file),
            "--no-error-summary",
            str(file_path),
        ],
        logger,
    )
    if mypy_exit != 0:
        issues.append(f"mypy:\n{mypy_out}")

    return issues


def _log_input_payload(payload: dict[str, object], logger: logging.Logger) -> None:
    logger.debug("input payload:\n%s", json.dumps(payload, indent=2, sort_keys=True))


def _should_skip_payload(payload: dict[str, object], logger: logging.Logger) -> bool:
    if _tool_name(payload) not in _WRITE_TOOLS:
        logger.info("Skipping unsupported tool: %s", _tool_name(payload))
        return True
    return False


def _build_issues_response(all_issues: list[str]) -> str:
    errors = "\n\n".join(all_issues)
    llm_msg = (
        "LINTING/TYPE ERRORS FOUND — the file was saved but is not clean.\n"
        "Do NOT stop. Do NOT report success.\n"
        "Do NOT proceed to any other step.\n"
        "Fix every error below using the file editing tool,"
        " then wait for the hook to confirm the file is clean."
    )
    return json.dumps(
        {
            # Claude-family / VS Code PostToolUse contract.
            "decision": "block",
            "reason": f"{llm_msg}\n\n{errors}",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": errors,
            },
            # COPILOT-ONLY: Copilot CLI output contract; other harnesses ignore these.
            "modifiedResult": {
                "resultType": "success",
                "textResultForLlm": llm_msg,
            },
            "additionalContext": errors,
        }
    )


def _collect_issues(payload: dict[str, object], logger: logging.Logger) -> list[str]:
    file_paths = _resolve_file_paths(payload)
    if not file_paths:
        logger.info("No Python files found in payload")
        return []
    # Use the session cwd as the config search boundary; no harness dir is assumed.
    workspace_root = Path(_payload_str(payload, "cwd", ".")).resolve()
    all_issues: list[str] = []
    for file_path in file_paths:
        all_issues.extend(_run_checks(file_path, workspace_root, logger))
    return all_issues


def main() -> None:
    payload: dict[str, object] = json.loads(sys.stdin.read())
    logger = _build_logger(_resolve_log_level())
    logger.info("python-quality hook invoked")
    logger.info("cwd: %s", _payload_str(payload, "cwd", "."))
    _log_input_payload(payload, logger)

    if _should_skip_payload(payload, logger):
        return

    all_issues = _collect_issues(payload, logger)
    if not all_issues:
        logger.info("Completed without issues")
        return

    print(_build_issues_response(all_issues))
    logger.info("Completed with issues")


if __name__ == "__main__":
    main()
