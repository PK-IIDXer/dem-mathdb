from __future__ import annotations


class DemError(Exception):
    """Base exception for the library, with optional machine-readable context."""

    def __init__(self, message: str, *, code: str | None = None,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details if details is not None else {}


class ValidationError(DemError):
    """Raised when input is syntactically or logically invalid."""


class FormulaValidationError(ValidationError):
    """Raised when formula construction validation fails."""

    def __init__(self, message: str, position: int | None = None, *,
                 code: str | None = None, details: dict[str, object] | None = None) -> None:
        super().__init__(message, code=code, details=details)
        self.position = position


class ProofValidationError(ValidationError):
    """Raised when proof-step validation fails."""

    def __init__(self, message: str, step_ord: int | None = None, *,
                 code: str | None = None, details: dict[str, object] | None = None) -> None:
        super().__init__(message, code=code, details=details)
        self.step_ord = step_ord


class NotFoundError(DemError):
    """Raised when a referenced record does not exist."""

    def __init__(self, entity: str, id: int | str, *, code: str | None = None,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(f"{entity} id={id!r} not found", code=code, details=details)
        self.entity = entity
        self.id = id


class ConflictError(DemError):
    """Raised when a registration conflicts with an existing record."""

    def __init__(self, entity: str, field: str, value: str, *, code: str | None = None,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(f"{entity}.{field}={value!r} already exists", code=code, details=details)
        self.entity = entity
        self.field = field
        self.value = value
