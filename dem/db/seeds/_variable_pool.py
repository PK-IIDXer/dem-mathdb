"""Content-neutral helpers for seed-owned free term variables."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import Symbol
from dem.errors import ValidationError
from dem.services.symbol import SymbolService
from dem.types import SymbolTypeName


def variable_name(name: str) -> str:
    return name


def ensure_variable(
    session: Session,
    name: str,
    *,
    remarks: str | None = None,
    symbols: SymbolService | None = None,
) -> Symbol:
    existing = session.scalar(select(Symbol).where(Symbol.name == name))
    if existing is not None:
        if existing.symbol_type.name != SymbolTypeName.FREE_TERM_VAR.value:
            raise ValidationError(f"variable name {name!r} has a different type")
        return existing
    symbols = symbols or SymbolService(session)
    type_row = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    return symbols.register(
        name,
        type_row.id,
        0,
        is_primitive=False,
        latex_template=name,
        remarks=remarks or "シード用自由項変数",
    )


def get_variable(session: Session, name: str) -> Symbol:
    row = session.scalar(select(Symbol).where(Symbol.name == name))
    if row is None:
        raise ValueError(f"variable {name!r} has not been seeded")
    return row


class SeedSymbolService(SymbolService):
    """Exact-name symbol service retained for seed-builder compatibility."""
