from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from dem.types import SymbolMeta


@dataclass(frozen=True)
class SurfaceSymbol:
    id: int
    name: str
    meta: SymbolMeta
    namespace: str
    notation_kind: str = "prefix"
    precedence: int | None = None


@dataclass(frozen=True)
class SymbolTable:
    """All information the parser/printer needs, with no database dependency."""

    symbols: Mapping[int, SurfaceSymbol]
    aliases: Mapping[str, int] = field(default_factory=dict)
    _lexer_root: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        symbols = dict(self.symbols)
        qualified_names = {
            f"{symbol.namespace}::{symbol.name}": symbol.id
            for symbol in symbols.values()
        }
        if len(qualified_names) != len(symbols):
            raise ValueError("qualified symbol names must be unique")
        ids_by_short_name: dict[str, list[int]] = {}
        for symbol in symbols.values():
            ids_by_short_name.setdefault(symbol.name, []).append(symbol.id)
        ambiguous_names = frozenset(
            name for name, ids in ids_by_short_name.items() if len(ids) > 1
        )
        names = {
            name: ids[0]
            for name, ids in ids_by_short_name.items()
            if name not in ambiguous_names
        }
        aliases = dict(self.aliases)
        collisions = (set(ids_by_short_name) | set(qualified_names)) & aliases.keys()
        if collisions:
            raise ValueError(f"aliases collide with symbol names: {min(collisions)!r}")
        missing = set(aliases.values()) - symbols.keys()
        if missing:
            raise ValueError(f"alias refers to unknown symbol: {min(missing)}")
        object.__setattr__(self, "symbols", MappingProxyType(symbols))
        object.__setattr__(self, "aliases", MappingProxyType(aliases))
        object.__setattr__(self, "_names", MappingProxyType(names))
        object.__setattr__(self, "_qualified_names", MappingProxyType(qualified_names))
        object.__setattr__(self, "ambiguous_names", ambiguous_names)

    @property
    def spellings(self) -> Mapping[str, int]:
        return MappingProxyType(
            {**self._qualified_names, **self._names, **self.aliases}
        )

    def resolve(self, spelling: str) -> SurfaceSymbol | None:
        symbol_id = self.aliases.get(
            spelling, self._qualified_names.get(spelling, self._names.get(spelling))
        )
        return self.symbols.get(symbol_id) if symbol_id is not None else None

    def spelling(self, symbol_id: int) -> str:
        symbol = self.get(symbol_id)
        if symbol.name in self.ambiguous_names:
            return f"{symbol.namespace}::{symbol.name}"
        return symbol.name

    def is_ambiguous(self, spelling: str) -> bool:
        return spelling in self.ambiguous_names

    def get(self, symbol_id: int) -> SurfaceSymbol:
        try:
            return self.symbols[symbol_id]
        except KeyError as exc:
            raise ValueError(f"unknown symbol id: {symbol_id}") from exc
