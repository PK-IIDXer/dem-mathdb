from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import Symbol
from dem.services.symbol import SymbolService
from dem.symbol_aliases import BUILTIN_ALIASES


def apply_builtin_aliases(session: Session) -> None:
    service = SymbolService(session)
    for alias, symbol_name in BUILTIN_ALIASES.items():
        symbol = session.scalar(select(Symbol).where(Symbol.name == symbol_name))
        if symbol is not None:
            service.add_alias(symbol.id, alias, source="builtin")
