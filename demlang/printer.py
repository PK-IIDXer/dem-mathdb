from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from dem.types import Token
from demlang.symbols import SurfaceSymbol, SymbolTable


_BOUND_NAME_BASES = ("x", "y", "z")


@dataclass
class _Node:
    token: Token
    children: list["_Node"]


def _read(tokens: Sequence[Token], pos: int, table: SymbolTable) -> tuple[_Node, int]:
    if pos >= len(tokens):
        raise ValueError("unexpected end of token sequence")
    token = tokens[pos]
    if token.is_bound_var:
        return _Node(token, []), pos + 1
    symbol = table.get(token.symbol_id or 0)
    child_count = 1 if symbol.meta.is_quantifier else symbol.meta.arity
    children: list[_Node] = []
    pos += 1
    for _ in range(child_count):
        child, pos = _read(tokens, pos, table)
        children.append(child)
    return _Node(token, children), pos


def _symbol_names(node: _Node, table: SymbolTable) -> set[str]:
    names: set[str] = set()
    if node.token.is_symbol:
        names.add(table.get(node.token.symbol_id or 0).name)
    for child in node.children:
        names.update(_symbol_names(child, table))
    return names


def _bound_name(depth: int, used: set[str]) -> str:
    cycle, offset = divmod(depth, len(_BOUND_NAME_BASES))
    base = _BOUND_NAME_BASES[offset]
    preferred = base if cycle == 0 else f"{base}_{cycle}"
    if preferred not in used:
        return preferred
    for suffix in ("′", "″"):
        candidate = f"{preferred}{suffix}"
        if candidate not in used:
            return candidate
    suffix = 1
    while f"{preferred}_{suffix}" in used:
        suffix += 1
    return f"{preferred}_{suffix}"


def _is_atomic(node: _Node, table: SymbolTable) -> bool:
    if node.token.is_bound_var:
        return True
    return table.get(node.token.symbol_id or 0).meta.arity == 0


def _render(node: _Node, table: SymbolTable, scope: list[str], used: set[str]) -> str:
    if node.token.is_bound_var:
        index = node.token.de_bruijn_index or 0
        if index >= len(scope):
            raise ValueError(f"unbound de Bruijn index: {index}")
        return scope[-1 - index]

    symbol = table.get(node.token.symbol_id or 0)
    spelling = table.spelling(symbol.id)
    if symbol.meta.is_quantifier:
        # Keep this in sync with FormulaEditor/model.ts. The naming contract is
        # documented in docs/design/overview/conventions.md §4.
        name = _bound_name(len(scope), used | set(scope))
        return f"{spelling} {name}. {_render(node.children[0], table, [*scope, name], used | {name})}"
    if symbol.meta.arity == 0:
        return spelling
    if symbol.notation_kind == "infix":
        left = _render(node.children[0], table, scope, used)
        right = _render(node.children[1], table, scope, used)
        if not _is_atomic(node.children[0], table):
            left = f"({left})"
        right_is_same_chain = bool(
            node.children[1].token.is_symbol
            and table.get(node.children[1].token.symbol_id or 0).id == symbol.id
            and symbol.notation_kind == "infix"
        )
        if not _is_atomic(node.children[1], table) and not right_is_same_chain:
            right = f"({right})"
        return f"{left} {spelling} {right}"
    rendered = ", ".join(_render(child, table, scope, used) for child in node.children)
    return f"{spelling}({rendered})"


def print_dss(tokens: Sequence[Token], table: SymbolTable) -> str:
    if not tokens:
        raise ValueError("formula is empty")
    root, end = _read(tokens, 0, table)
    if end != len(tokens):
        raise ValueError(f"trailing tokens at position {end}")
    # A scoped name may shadow an unused global spelling safely because the
    # parser resolves scope first. Only spellings present in this formula can
    # be captured. See docs/design/overview/conventions.md §4.
    return _render(root, table, [], _symbol_names(root, table))
