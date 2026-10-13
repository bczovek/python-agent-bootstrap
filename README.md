# Python Agent Bootstrap

APM package with a Python coding-standards instruction and a post-edit quality hook. The hook runs `ruff` and `mypy` on every Python file the agent creates or edits and feeds the errors back to the agent.

## Install in another project
Requires the [APM CLI](https://github.com/microsoft/apm), plus `ruff` and `mypy` on `PATH` and a `python` executable for the hook.

From the root of the consuming project:
```
apm install bczovek/python-agent-bootstrap
```
This adds the package to the project's `apm.yml` and deploys its instruction and hook for the detected runtime (use `--target <runtime>`, e.g. `--target copilot`, to pick one). Equivalent manual form in `apm.yml`:
```yaml
dependencies:
  apm:
    - bczovek/python-agent-bootstrap
```
then run `apm install`. To pin a version, append a git ref: `bczovek/python-agent-bootstrap#v1.0.0`. Update later with `apm update`.

The instruction applies to `**/*.py`. Edit the `applyTo` pattern if you need a narrower scope.

## Usage
No explicit action is needed. The instruction is applied whenever the agent works on Python files. After each file write the hook checks the file and, if there are issues, asks the agent to fix them before continuing.

The hook formats the file with `ruff format`, then runs `ruff check` and `mypy`. It uses the consuming project's ruff and mypy config when it finds one between the file and the session `cwd`. Otherwise it falls back to the bundled [pyproject.toml](.apm/hooks/python-quality/pyproject.toml).

Set the `LOG_LEVEL` environment variable (default `INFO`) to change log verbosity. Logs are written to `~/.apm/hooks/debug/python-quality.log`.

## Contents (`.apm/`)
| Type | Name | Purpose |
| - | - | - |
| instruction | `python` | Applies to `**/*.py`: mandatory type hints, OOP principles, naming conventions and general rules. |
| hook | `python-quality` | `PostToolUse` hook that runs `ruff format`, `ruff check` and `mypy` on files written by the agent. |

## Harness support
The hook reads both Claude-style (`tool_name`, `tool_input`) and Copilot CLI-style (`toolName`, `toolArgs`) payloads and returns a response both families understand. Harnesses that name their file-writing tools differently need those names added to `_WRITE_TOOLS` in [python-quality.py](.apm/hooks/python-quality/python-quality.py). Hooks are not deployed to targets that do not support them (for example `opencode`).
