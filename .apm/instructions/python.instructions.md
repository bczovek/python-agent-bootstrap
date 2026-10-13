---
description: Use when creating or modifying Python source files to enforce coding standards.
applyTo: "**/*.py"
---

# Python Coding Standards

## Type Hints — Mandatory Everywhere

- Every function and method must have type annotations on all parameters and the return type (including `-> None`).
- Every `*args` and `**kwargs` must be annotated (e.g., `*args: int`, `**kwargs: str`).
- Every variable assignment at module level, class level, and inside `__init__` must be annotated (e.g., `self.name: str = name`).
- Use `ClassVar[T]` for class-level variables that are not instance attributes.
- Use `Final` for constants that must not be reassigned.
- Use `T | None` for nullable types — never use `Optional[T]` (Python 3.10+). Never leave an argument that may be `None` unannotated.
- Use `X | Y` for union types — never use `Union[X, Y]`.
- Use `Callable[[ArgType], ReturnType]` when annotating function-valued variables or parameters.
- Use `Protocol` for structural typing instead of concrete base classes when the relationship is purely behavioral.
- Never use bare `Any` without a comment explaining why it is unavoidable.

## OOP Principles

### Single Responsibility
- Each class must have exactly one reason to change.
- If a class requires more than ~5 public methods, consider splitting it into smaller classes.

### Encapsulation
- Default all attributes to protected (`_name`) unless they form part of the public API.
- Use `__name` (name mangling) for attributes that must not be accessed or overridden outside the class.
- Never expose raw mutable internal state directly; use `@property` with an optional setter.
- Use `@property` instead of `get_x()` / `set_x()` method pairs.

### Inheritance and Composition
- Prefer composition over inheritance.
- Use inheritance only for true "is-a" relationships.
- Never inherit from a class solely to reuse its implementation — extract shared logic into a helper class or standalone function instead.
- All subclasses must satisfy the Liskov Substitution Principle: a subclass instance must be usable wherever its base class is expected without altering correctness.
- Define abstract interfaces using `abc.ABC` and `@abstractmethod`; every abstract method must be implemented by concrete subclasses.

### Dependency Inversion
- Depend on abstractions (`ABC`, `Protocol`), not on concrete implementations.
- Inject dependencies through the constructor rather than instantiating them inside the class.

### Law of Demeter
- A method may only call methods on: `self`, objects passed as parameters, objects it creates, or direct component attributes.
- Never chain calls that reach into the internals of another object (e.g., `a.b.c.do_something()`).

## Naming Conventions

- Class names must be nouns.
- Method and function names must be verbs or verb phrases.
- Boolean variables and properties should be prefixed with `is_`, `has_`, or `can_` (e.g., `is_valid`, `has_children`).

## General Rules

- Functions and methods must be small and focused — ideally no longer than 20 lines. If a function grows beyond this, extract logical sub-steps into well-named helper functions.
- A function must do exactly one thing. If its name requires "and", it should be split.
- Never silence exceptions with a bare `except:` clause; always catch a specific exception type.
- Define custom exception classes (inheriting from `Exception` or a relevant stdlib exception) instead of raising generic `Exception` or `ValueError` directly.
- One python file should contain at most one class with logic. Exception classes and data classes are allowed to be defined in the same file as the main class if they are closely related, but otherwise should be split into separate files.
