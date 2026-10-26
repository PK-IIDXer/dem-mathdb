from __future__ import annotations

from collections.abc import Callable

import pytest

from dem.types import FormulaTypeName, SymbolMeta, SymbolTypeName, Token
from demlang import DemlangSyntaxError, parse_convenience, parse_core, print_dss
from demlang.symbols import SurfaceSymbol, SymbolTable


Parser = Callable[[str, SymbolTable], list[Token]]


def _meta(
    arity: int,
    symbol_type: SymbolTypeName,
    output: FormulaTypeName,
    input_: FormulaTypeName | None,
) -> SymbolMeta:
    return SymbolMeta(
        arity=arity,
        symbol_type_name=symbol_type,
        output_formula_type=output,
        input_formula_type=input_,
        is_quantifier=False,
    )


def _table() -> SymbolTable:
    term_atom = _meta(0, SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None)
    prop_atom = _meta(
        0, SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, None
    )
    function = _meta(
        2, SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM
    )
    logical = _meta(
        2,
        SymbolTypeName.LOGICAL,
        FormulaTypeName.PROPOSITION,
        FormulaTypeName.PROPOSITION,
    )
    symbols = {
        1: SurfaceSymbol(1, "x", term_atom, "test"),
        2: SurfaceSymbol(2, "y", term_atom, "test"),
        3: SurfaceSymbol(3, "z", term_atom, "test"),
        4: SurfaceSymbol(4, "A", function, "test", "infix", 55),
        5: SurfaceSymbol(5, "B", function, "test", "infix", 55),
        6: SurfaceSymbol(6, "a", prop_atom, "test"),
        7: SurfaceSymbol(7, "b", prop_atom, "test"),
        8: SurfaceSymbol(8, "c", prop_atom, "test"),
        9: SurfaceSymbol(9, "⇒", logical, "test", "infix", 20),
    }
    return SymbolTable(symbols)


@pytest.mark.parametrize("parser", (parse_core, parse_convenience))
def test_same_precedence_nonlogical_infix_guard(parser: Parser) -> None:
    table = _table()
    text = "x A y B z"

    with pytest.raises(DemlangSyntaxError) as caught:
        parser(text, table)

    assert caught.value.code == "formula.same_precedence_infix"
    assert caught.value.position == text.index("B")
    assert parser("(x A y) B z", table) != parser("x A (y B z)", table)


def test_nonlogical_printer_parentheses_make_the_output_round_trip() -> None:
    table = _table()
    tokens = [
        Token(symbol_id=4),
        Token(symbol_id=1),
        Token(symbol_id=4),
        Token(symbol_id=2),
        Token(symbol_id=3),
    ]

    rendered = print_dss(tokens, table)

    assert rendered == "x A (y A z)"
    assert parse_core(rendered, table) == tokens
    assert parse_convenience(rendered, table) == tokens


def test_logical_right_associative_chain_is_unchanged() -> None:
    table = _table()
    tokens = parse_core("a ⇒ b ⇒ c", table)

    assert tokens == parse_core("a ⇒ (b ⇒ c)", table)
    assert tokens == parse_convenience("a ⇒ b ⇒ c", table)
    assert print_dss(tokens, table) == "a ⇒ b ⇒ c"
