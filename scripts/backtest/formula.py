"""`formula_token` の polish notation + de Bruijn を Lean 4 の項へ写す。

設計: `docs/design/ops/external-verification-backtest.md` §4.2 / §4.3

ここは**変換だけ**を行う。代入も抽象も分解も計算しない (設計 §5.1)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from scripts.backtest.dem_db import (
    BacktestError,
    CONNECTIVE,
    FREE_PROP_VAR,
    FREE_TERM_VAR,
    FUNCTION,
    PREDICATE,
    PROP_BINDER,
    Symbol,
    TERM_BINDER,
    Token,
)


@dataclass(frozen=True)
class Node:
    """論理式の構文木。`symbol_id` か `de_bruijn_index` のどちらか一方を持つ。"""

    symbol_id: int | None
    de_bruijn_index: int | None
    children: tuple["Node", ...]


def child_count(symbol: Symbol) -> int:
    """量化記号は arity によらず本体 1 つを取る (DEM の `validate_tokens` と同じ)。"""
    return 1 if symbol.is_quantifier else symbol.arity


def parse(tokens: list[Token], symbols: dict[int, Symbol]) -> Node:
    node, next_pos = _parse_at(tokens, 0, symbols)
    if next_pos != len(tokens):
        raise BacktestError(f"trailing tokens at position {next_pos}")
    return node


def _parse_at(tokens: list[Token], pos: int, symbols: dict[int, Symbol]) -> tuple[Node, int]:
    if pos >= len(tokens):
        raise BacktestError("unexpected end of tokens")
    token = tokens[pos]
    if token.symbol_id is None:
        if token.de_bruijn_index is None:
            raise BacktestError(f"token at {pos} is neither a symbol nor a bound variable")
        return Node(None, token.de_bruijn_index, ()), pos + 1

    symbol = symbols.get(token.symbol_id)
    if symbol is None:
        raise BacktestError(f"unknown symbol id {token.symbol_id}")
    children: list[Node] = []
    cur = pos + 1
    for _ in range(child_count(symbol)):
        child, cur = _parse_at(tokens, cur, symbols)
        children.append(child)
    return Node(symbol.id, None, tuple(children)), cur


def free_symbol_ids(node: Node, symbols: dict[int, Symbol]) -> set[int]:
    """論理式に現れる自由変数記号 (項型・命題型) の id。"""
    found: set[int] = set()
    _collect_free(node, symbols, found)
    return found


def _collect_free(node: Node, symbols: dict[int, Symbol], found: set[int]) -> None:
    if node.symbol_id is not None and symbols[node.symbol_id].is_free_variable:
        found.add(node.symbol_id)
    for child in node.children:
        _collect_free(child, symbols, found)


def constant_name(symbol_id: int) -> str:
    """記号の Lean 識別子。

    読みやすい別名は付けない —— `Neg` などは Lean core の宣言と衝突する (設計 §4.2)。
    """
    return f"dem_s{symbol_id}"


def variable_name(symbol_id: int) -> str:
    """自由変数記号に対応する Lean のパラメータ名。"""
    return f"v{symbol_id}"


def bound_name(binder_depth: int) -> str:
    return f"z{binder_depth}"


def _arrow(parts: Iterable[str]) -> str:
    return " → ".join(parts)


def constant_type(symbol: Symbol) -> str:
    """§4.2 の表。`is_primitive` では分岐しない。"""
    if symbol.type_name == FUNCTION:
        return _arrow(["U"] * symbol.arity + ["U"])
    if symbol.type_name == PREDICATE:
        return _arrow(["U"] * symbol.arity + ["Prop"])
    if symbol.type_name == CONNECTIVE:
        return _arrow(["Prop"] * symbol.arity + ["Prop"])
    if symbol.type_name == PROP_BINDER:
        return "(U → Prop) → Prop"
    if symbol.type_name == TERM_BINDER:
        return "(U → Prop) → U"
    raise BacktestError(f"symbol {symbol.name!r} is a free variable, not a constant")


def parameter_type(symbol: Symbol) -> str:
    if symbol.type_name == FREE_TERM_VAR:
        return "U"
    if symbol.type_name == FREE_PROP_VAR:
        return _arrow(["U"] * symbol.arity + ["Prop"])
    raise BacktestError(f"symbol {symbol.name!r} is not a free variable")


class Renderer:
    """構文木 → Lean 項。

    `→` と `∀` だけを Lean の構文へ写す (設計 §4.1)。どちらも `symbol_role` が同定する。
    """

    def __init__(
        self,
        symbols: dict[int, Symbol],
        implication_id: int,
        universal_id: int,
    ) -> None:
        self._symbols = symbols
        self._implication_id = implication_id
        self._universal_id = universal_id

    def render(self, node: Node, depth: int = 0) -> str:
        return self._render(node, depth)[0]

    def _render(self, node: Node, depth: int) -> tuple[str, frozenset[int]]:
        """項と、その項に自由な de Bruijn index の集合を返す。

        index の集合は束縛子が実際に使われているかの判定に使う。使われていない
        束縛子を `z0` のまま出すと Lean の `unusedVariables` linter が鳴るので、
        `_z0` に落とす。DEM 側では公理 7 `φ → ∀(φ)` のように普通に起きる。
        """
        if node.symbol_id is None:
            index = node.de_bruijn_index
            assert index is not None
            binder_depth = depth - 1 - index
            if binder_depth < 0:
                raise BacktestError(
                    f"unbound de Bruijn index {index} at binder depth {depth}"
                )
            return bound_name(binder_depth), frozenset({index})

        symbol = self._symbols[node.symbol_id]

        if symbol.is_quantifier:
            body, body_free = self._render(node.children[0], depth + 1)
            name = bound_name(depth) if 0 in body_free else f"_{bound_name(depth)}"
            free = frozenset(index - 1 for index in body_free if index >= 1)
            if symbol.id == self._universal_id:
                return f"(∀ {name} : U, {body})", free
            return f"({constant_name(symbol.id)} (fun ({name} : U) => {body}))", free

        rendered = [self._render(child, depth) for child in node.children]
        free = frozenset().union(*(item[1] for item in rendered)) if rendered else frozenset()

        if symbol.id == self._implication_id:
            left, right = (item[0] for item in rendered)
            return f"({left} → {right})", free

        head = variable_name(symbol.id) if symbol.is_free_variable else constant_name(symbol.id)
        if not rendered:
            return head, free
        args = " ".join(item[0] for item in rendered)
        return f"({head} {args})", free

    def binders(self, symbol_ids: Iterable[int]) -> str:
        """自由変数記号を Lean の束縛子列にする。id 順で決定的に並べる。"""
        parts = []
        for symbol_id in sorted(symbol_ids):
            symbol = self._symbols[symbol_id]
            parts.append(f"({variable_name(symbol_id)} : {parameter_type(symbol)})")
        return " ".join(parts)
