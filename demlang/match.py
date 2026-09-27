from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from dem.types import SymbolMeta, SymbolTypeName, Token


@dataclass(frozen=True)
class PropBinding:
    body_tokens: tuple[Token, ...]
    parameter_de_bruijn_index: int | None = None


@dataclass
class MatchResult:
    term_substs: dict[int, tuple[Token, ...]] = field(default_factory=dict)
    prop_substs: dict[int, PropBinding] = field(default_factory=dict)
    undetermined: set[int] = field(default_factory=set)


def _shift_bound_tokens(
    tokens: Sequence[Token],
    delta: int,
    symbol_meta: Mapping[int, SymbolMeta],
) -> list[Token]:
    shifted: list[Token] = []

    def visit(pos: int, depth: int) -> int:
        token = tokens[pos]
        if token.is_bound_var:
            index = token.de_bruijn_index or 0
            shifted.append(
                Token(de_bruijn_index=index + delta) if index >= depth else token
            )
            return pos + 1

        shifted.append(token)
        meta = symbol_meta[token.symbol_id or 0]
        pos += 1
        child_depth = depth + 1 if meta.is_quantifier else depth
        for _ in range(1 if meta.is_quantifier else meta.arity):
            pos = visit(pos, child_depth)
        return pos

    end = visit(0, 0)
    if end != len(tokens):
        raise ValueError(f"trailing tokens at position {end}")
    return shifted


def subtree_end(
    tokens: Sequence[Token], pos: int, symbol_meta: Mapping[int, SymbolMeta]
) -> int:
    if pos >= len(tokens):
        raise ValueError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        return pos + 1
    meta = symbol_meta[token.symbol_id or 0]
    pos += 1
    for _ in range(1 if meta.is_quantifier else meta.arity):
        pos = subtree_end(tokens, pos, symbol_meta)
    return pos


def match_formula(
    pattern: Sequence[Token],
    target: Sequence[Token],
    symbol_meta: Mapping[int, SymbolMeta],
    result: MatchResult | None = None,
) -> MatchResult | None:
    """Match one DEM formula pattern without consulting a database.

    Term variables and nullary proposition variables are first-order schema
    variables. Unary proposition variables are accepted for the Miller-pattern
    case where their sole argument is a bound variable.
    """
    matched = MatchResult(
        term_substs=dict(result.term_substs) if result else {},
        prop_substs=dict(result.prop_substs) if result else {},
        undetermined=set(result.undetermined) if result else set(),
    )
    positions = _match(pattern, 0, target, 0, symbol_meta, matched)
    if positions is None or positions != (len(pattern), len(target)):
        return None
    if result is not None:
        result.term_substs.clear()
        result.term_substs.update(matched.term_substs)
        result.prop_substs.clear()
        result.prop_substs.update(matched.prop_substs)
        result.undetermined.clear()
        result.undetermined.update(matched.undetermined)
        return result
    return matched


def match_formulas(
    constraints: Sequence[tuple[Sequence[Token], Sequence[Token]]],
    symbol_meta: Mapping[int, SymbolMeta],
    result: MatchResult | None = None,
) -> MatchResult | None:
    """Match related formulas, prioritizing constraints that reveal Miller bodies."""
    matched = MatchResult(
        term_substs=dict(result.term_substs) if result else {},
        prop_substs=dict(result.prop_substs) if result else {},
        undetermined=set(result.undetermined) if result else set(),
    )
    pending = list(constraints)
    while pending:
        index = next(
            (
                i
                for i, (pattern, _target) in enumerate(pending)
                if _contains_seedable_miller(
                    pattern, 0, len(pattern), symbol_meta, matched
                )
            ),
            0,
        )
        pattern, target = pending.pop(index)
        if match_formula(pattern, target, symbol_meta, matched) is None:
            return None
    if result is not None:
        result.term_substs.clear()
        result.term_substs.update(matched.term_substs)
        result.prop_substs.clear()
        result.prop_substs.update(matched.prop_substs)
        result.undetermined.clear()
        result.undetermined.update(matched.undetermined)
        return result
    return matched


def _match_prop_binding(
    binding: PropBinding,
    argument_pattern: Sequence[Token],
    target: Sequence[Token],
    target_pos: int,
    meta_by_id: Mapping[int, SymbolMeta],
    result: MatchResult,
) -> int | None:
    parameter_index = binding.parameter_de_bruijn_index
    if parameter_index is None:
        return None

    def visit(pos: int, current_target: int, local_depth: int) -> tuple[int, int] | None:
        if current_target >= len(target):
            return None
        token = binding.body_tokens[pos]
        if token.is_bound_var:
            if token.de_bruijn_index == parameter_index + local_depth:
                positions = _match(
                    _shift_bound_tokens(argument_pattern, local_depth, meta_by_id),
                    0,
                    target,
                    current_target,
                    meta_by_id,
                    result,
                )
                if positions is None or positions[0] != len(argument_pattern):
                    return None
                return pos + 1, positions[1]
            if target[current_target] != token:
                return None
            return pos + 1, current_target + 1
        target_token = target[current_target]
        if not target_token.is_symbol or target_token.symbol_id != token.symbol_id:
            return None
        meta = meta_by_id[token.symbol_id or 0]
        pos += 1
        current_target += 1
        child_depth = local_depth + 1 if meta.is_quantifier else local_depth
        for _ in range(1 if meta.is_quantifier else meta.arity):
            positions = visit(pos, current_target, child_depth)
            if positions is None:
                return None
            pos, current_target = positions
        return pos, current_target

    positions = visit(0, target_pos, 0)
    if positions is None or positions[0] != len(binding.body_tokens):
        return None
    return positions[1]


def _contains_seedable_miller(
    tokens: Sequence[Token],
    start: int,
    end: int,
    meta_by_id: Mapping[int, SymbolMeta],
    result: MatchResult,
) -> bool:
    for pos in range(start, end - 1):
        token = tokens[pos]
        if not token.is_symbol:
            continue
        symbol_id = token.symbol_id or 0
        meta = meta_by_id[symbol_id]
        if (
            meta.symbol_type_name == SymbolTypeName.FREE_PROP_VAR
            and meta.arity == 1
            and symbol_id not in result.prop_substs
            and tokens[pos + 1].is_bound_var
        ):
            return True
    return False


def _match(
    pattern: Sequence[Token],
    ppos: int,
    target: Sequence[Token],
    tpos: int,
    meta_by_id: Mapping[int, SymbolMeta],
    result: MatchResult,
) -> tuple[int, int] | None:
    if ppos >= len(pattern) or tpos >= len(target):
        return None
    ptoken = pattern[ppos]
    tend = subtree_end(target, tpos, meta_by_id)

    if ptoken.is_bound_var:
        if ptoken != target[tpos]:
            return None
        return ppos + 1, tpos + 1

    symbol_id = ptoken.symbol_id or 0
    meta = meta_by_id[symbol_id]
    if meta.symbol_type_name == SymbolTypeName.FREE_TERM_VAR:
        value = tuple(target[tpos:tend])
        previous = result.term_substs.get(symbol_id)
        if previous is not None and previous != value:
            return None
        result.term_substs[symbol_id] = value
        return ppos + 1, tend

    if meta.symbol_type_name == SymbolTypeName.FREE_PROP_VAR:
        if meta.arity == 0:
            value = PropBinding(tuple(target[tpos:tend]))
            previous = result.prop_substs.get(symbol_id)
            if previous is not None and previous != value:
                return None
            result.prop_substs[symbol_id] = value
            return ppos + 1, tend
        pattern_end = ppos + 1
        try:
            for _ in range(meta.arity):
                pattern_end = subtree_end(pattern, pattern_end, meta_by_id)
        except (IndexError, ValueError):
            return None
        if meta.arity >= 1:
            target_token = target[tpos]
            if target_token.is_symbol and target_token.symbol_id == symbol_id:
                pcur = ppos + 1
                tcur = tpos + 1
                for _ in range(meta.arity):
                    positions = _match(
                        pattern, pcur, target, tcur, meta_by_id, result
                    )
                    if positions is None:
                        return None
                    pcur, tcur = positions
                return pcur, tcur
        if meta.arity == 1:
            argument_end = pattern_end
            previous = result.prop_substs.get(symbol_id)
            if previous is not None:
                matched_end = _match_prop_binding(
                    previous,
                    pattern[ppos + 1:argument_end],
                    target,
                    tpos,
                    meta_by_id,
                    result,
                )
                if matched_end != tend:
                    return None
                return argument_end, tend
            if not pattern[ppos + 1].is_bound_var or argument_end != ppos + 2:
                result.undetermined.add(symbol_id)
                return argument_end, tend
            parameter_index = pattern[ppos + 1].de_bruijn_index
            value = PropBinding(tuple(target[tpos:tend]), parameter_index)
            result.prop_substs[symbol_id] = value
            result.undetermined.discard(symbol_id)
            return ppos + 2, tend
        if meta.arity > 1:
            result.undetermined.add(symbol_id)
            return pattern_end, tend
        return None

    ttoken = target[tpos]
    if not ttoken.is_symbol or ttoken.symbol_id != symbol_id:
        return None
    pcur = ppos + 1
    tcur = tpos + 1
    children: list[tuple[int, int, int, int]] = []
    for _ in range(1 if meta.is_quantifier else meta.arity):
        pend = subtree_end(pattern, pcur, meta_by_id)
        target_end = subtree_end(target, tcur, meta_by_id)
        children.append((pcur, pend, tcur, target_end))
        pcur, tcur = pend, target_end
    children.sort(
        key=lambda child: not _contains_seedable_miller(
            pattern, child[0], child[1], meta_by_id, result
        )
    )
    for child_pstart, child_pend, child_tstart, child_tend in children:
        positions = _match(
            pattern, child_pstart, target, child_tstart, meta_by_id, result
        )
        if positions != (child_pend, child_tend):
            return None
    return pcur, tcur
