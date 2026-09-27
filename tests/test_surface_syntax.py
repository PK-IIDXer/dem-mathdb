from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import FormulaToken, Symbol, SymbolAlias, SymbolType
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.types import FormulaTypeName, SymbolMeta, SymbolTypeName, Token
from demlang import DemlangSyntaxError, Lexer, parse_convenience, parse_core, print_dss
from demlang.match import match_formula
from demlang.printer import _bound_name
from demlang.symbols import SurfaceSymbol, SymbolTable


def _all_formula_tokens(session: Session) -> Iterator[tuple[int, list[Token]]]:
    rows = session.execute(
        select(
            FormulaToken.formula_id,
            FormulaToken.symbol_id,
            FormulaToken.de_bruijn_index,
        )
        .order_by(FormulaToken.formula_id, FormulaToken.position)
        .execution_options(yield_per=10_000)
    )
    formula_id: int | None = None
    tokens: list[Token] = []
    for row_formula_id, symbol_id, de_bruijn_index in rows:
        if formula_id is not None and row_formula_id != formula_id:
            yield formula_id, tokens
            tokens = []
        formula_id = row_formula_id
        tokens.append(
            Token(symbol_id=symbol_id)
            if symbol_id is not None
            else Token(de_bruijn_index=de_bruijn_index)
        )
    if formula_id is not None:
        yield formula_id, tokens


def test_round_trip_all_formulas(all_seeded_session: Session) -> None:
    table = FormulaService(all_seeded_session).surface_symbol_table()
    formula_count = 0
    for formula_id, tokens in _all_formula_tokens(all_seeded_session):
        rendered = print_dss(tokens, table)
        assert parse_core(rendered, table) == tokens, formula_id
        assert parse_convenience(rendered, table) == tokens, formula_id
        formula_count += 1
    assert formula_count == 8


def test_printer_avoids_shadowing(all_seeded_session: Session) -> None:
    symbols = SymbolService(all_seeded_session)
    table = FormulaService(all_seeded_session).surface_symbol_table()
    universal = symbols.get_by_role("universal_quantifier")
    equality = symbols.get_by_role("equality")
    free_x = symbols.get_by_name("x")
    tokens = [
        Token(symbol_id=universal.id),
        Token(symbol_id=equality.id),
        Token(de_bruijn_index=0),
        Token(symbol_id=free_x.id),
    ]

    rendered = print_dss(tokens, table)
    assert rendered.startswith(f"{universal.name} x′.")
    assert parse_core(rendered, table) == tokens


def test_printer_avoids_zero_arity_constant_shadowing() -> None:
    table = SymbolTable(
        {
            1: SurfaceSymbol(
                id=1,
                name="∀",
                namespace="dem.foundation.logic",
                meta=SymbolMeta(
                    arity=1,
                    symbol_type_name=SymbolTypeName.QUANT_TERM,
                    output_formula_type=FormulaTypeName.TERM,
                    input_formula_type=FormulaTypeName.TERM,
                    is_quantifier=True,
                ),
            ),
            2: SurfaceSymbol(
                id=2,
                name="x",
                namespace="dem.foundation.logic",
                meta=SymbolMeta(
                    arity=0,
                    symbol_type_name=SymbolTypeName.FUNCTION,
                    output_formula_type=FormulaTypeName.TERM,
                    input_formula_type=FormulaTypeName.TERM,
                    is_quantifier=False,
                ),
            ),
        }
    )
    tokens = [Token(symbol_id=1), Token(symbol_id=2)]

    rendered = print_dss(tokens, table)
    assert rendered == "∀ x′. x"
    assert parse_core(rendered, table) == tokens


def test_bound_name_golden_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "bound_names.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    for item in cases:
        assert _bound_name(item["depth"], set(item["avoid"])) == item["expected"]


def test_max_binder_depth_15_renders(all_seeded_session: Session) -> None:
    symbols = SymbolService(all_seeded_session)
    table = FormulaService(all_seeded_session).surface_symbol_table()
    universal = symbols.get_by_role("universal_quantifier")
    equality = symbols.get_by_role("equality")
    tokens = [Token(symbol_id=universal.id) for _ in range(15)] + [
        Token(symbol_id=equality.id),
        Token(de_bruijn_index=0),
        Token(de_bruijn_index=14),
    ]

    rendered = print_dss(tokens, table)
    assert parse_core(rendered, table) == tokens
    binder_names = re.findall(r"\S+ ([^.\s]+)\.", rendered)
    formula_names = {
        table.get(token.symbol_id or 0).name for token in tokens if token.is_symbol
    }
    assert not (set(binder_names) & formula_names)
    assert len(binder_names) == 15
    assert len(set(binder_names)) == len(binder_names)


def test_lexer_longest_match(all_seeded_session: Session) -> None:
    table = FormulaService(all_seeded_session).surface_symbol_table()
    lexer = Lexer(table)
    names = sorted(symbol.name for symbol in table.symbols.values())
    prefix_pairs = [
        (short, long)
        for short in names
        for long in names
        if short != long and long.startswith(short)
    ]
    assert prefix_pairs == [("φ", "φ¹"), ("ψ", "ψ¹")]
    for _short, long in prefix_pairs:
        lexemes = lexer.tokenize(long)
        assert len(lexemes) == 2
        assert lexemes[0].text == long
        assert lexemes[0].symbol_id == table.resolve(long).id


def test_parse_errors_carry_position(all_seeded_session: Session) -> None:
    table = FormulaService(all_seeded_session).surface_symbol_table()
    with pytest.raises(DemlangSyntaxError) as caught:
        parse_core("(unknown", table)
    assert caught.value.position == 1

    with pytest.raises(DemlangSyntaxError) as typed:
        parse_core("x → x", table)
    assert typed.value.position == 2


def test_truncated_higher_arity_pattern_is_not_a_match(
    all_seeded_session: Session,
) -> None:
    symbols = SymbolService(all_seeded_session)
    formulas = FormulaService(all_seeded_session)
    prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    phi2 = symbols.register("φ²", prop_type.id, 2)
    x = symbols.get_by_name("x")
    phi = symbols.get_by_name("φ")
    pattern = [Token(symbol_id=phi2.id), Token(symbol_id=x.id)]
    target = [Token(symbol_id=phi.id)]
    meta = formulas._load_symbol_meta([*pattern, *target])
    assert match_formula(pattern, target, meta) is None


def test_builtin_aliases_and_public_variables(all_seeded_session: Session) -> None:
    aliases = {
        row.alias: row.symbol_id
        for row in all_seeded_session.scalars(select(SymbolAlias))
    }
    symbols = SymbolService(all_seeded_session)
    assert aliases["forall"] == symbols.get_by_role("universal_quantifier").id
    assert aliases["->"] == symbols.get_by_role("implication").id

    variable_names = {
        row.name
        for row in all_seeded_session.scalars(
            select(Symbol)
            .join(SymbolType, Symbol.symbol_type_id == SymbolType.id)
            .where(SymbolType.name == SymbolTypeName.FREE_TERM_VAR.value)
        )
    }
    assert variable_names == {"t", "x", "y"}
