from __future__ import annotations

from dem.types import FormulaTypeName


class DemlangSyntaxError(ValueError):
    """A surface-syntax error with a source character position."""

    def __init__(
        self,
        message: str,
        position: int,
        *,
        expected_type: FormulaTypeName | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.position = position
        self.expected_type = expected_type
        self.code = code
