"""Generic display helpers used by the A-only public seed."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import Symbol
from dem.errors import ConflictError
from dem.services.symbol import SymbolService, symbol_shape


def symbol_latex(name: str, default: str) -> str:
    """Return a caller-provided template; the public seed has no overrides."""
    del name
    return default


def predicate_latex(name: str, default: str) -> str:
    return symbol_latex(name, default)


def notation_for(name: str) -> tuple[str, int | None]:
    del name
    return ("prefix", None)


def apply_notation(session: Session, templates: Mapping[str, str]) -> None:
    symbols = SymbolService(session)
    for name, template in templates.items():
        symbol = session.scalar(select(Symbol).where(Symbol.name == name))
        if symbol is not None:
            symbols.set_latex_template(symbol.id, template)


def apply_symbol_notation(session: Session) -> None:
    """Validate the display shapes assigned by the public seed."""
    validate_display_shapes(session)


def apply_predicate_notation(session: Session) -> None:
    del session


def apply_infix_notation(session: Session) -> None:
    del session


def validate_display_shapes(session: Session) -> None:
    seen: dict[tuple, Symbol] = {}
    for symbol in session.scalars(select(Symbol)):
        signature = symbol_shape(symbol)
        if signature in seen:
            other = seen[signature]
            raise ConflictError(
                "Symbol",
                "display",
                f"{other.name} / {symbol.name}: {signature}",
                code="symbol.display_collision",
            )
        seen[signature] = symbol
