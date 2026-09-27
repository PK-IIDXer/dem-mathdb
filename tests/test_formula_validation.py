from __future__ import annotations

import pytest

from dem.errors import FormulaValidationError
from dem.services.formula import validate_tokens
from dem.types import FormulaTypeName, SymbolMeta, SymbolTypeName, Token


def meta(
    symbol_type_name: SymbolTypeName,
    output: FormulaTypeName,
    input_type: FormulaTypeName | None,
    arity: int,
    is_quantifier: bool = False,
) -> SymbolMeta:
    return SymbolMeta(
        arity=arity,
        symbol_type_name=symbol_type_name,
        output_formula_type=output,
        input_formula_type=input_type,
        is_quantifier=is_quantifier,
    )


def test_validate_simple_implication() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.LOGICAL, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, 2),
        2: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 0),
    }

    result = validate_tokens(
        [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=2)],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION


def test_validate_quantified_predicate_with_bound_var() -> None:
    symbol_meta = {
        1: meta(
            SymbolTypeName.QUANT_PROP,
            FormulaTypeName.PROPOSITION,
            FormulaTypeName.PROPOSITION,
            1,
            is_quantifier=True,
        ),
        2: meta(SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
    }

    result = validate_tokens(
        [Token(symbol_id=1), Token(symbol_id=2), Token(de_bruijn_index=0)],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION


def test_unbound_de_bruijn_index_is_rejected() -> None:
    with pytest.raises(FormulaValidationError) as exc_info:
        validate_tokens([Token(de_bruijn_index=0)], {})

    assert exc_info.value.position == 0


def test_prop_var_argument_accepts_a_compound_term() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
        2: meta(SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, 1),
        3: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
    }

    result = validate_tokens(
        [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=3)],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION


def test_prop_var_arguments_are_parsed_as_separate_term_subtrees() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 2),
        2: meta(SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, 1),
        3: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
        4: meta(SymbolTypeName.FUNCTION, FormulaTypeName.TERM, FormulaTypeName.TERM, 2),
        5: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
    }

    result = validate_tokens(
        [
            Token(symbol_id=1),
            Token(symbol_id=2),
            Token(symbol_id=3),
            Token(symbol_id=4),
            Token(symbol_id=3),
            Token(symbol_id=5),
        ],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION


def test_prop_var_argument_rejects_a_proposition() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
        2: meta(SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
        3: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
    }

    with pytest.raises(FormulaValidationError) as exc_info:
        validate_tokens(
            [Token(symbol_id=1), Token(symbol_id=2), Token(symbol_id=3)],
            symbol_meta,
        )

    assert exc_info.value.position == 1


def test_prop_var_argument_accepts_a_term_quantifier() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
        2: meta(
            SymbolTypeName.QUANT_TERM,
            FormulaTypeName.TERM,
            FormulaTypeName.PROPOSITION,
            1,
            is_quantifier=True,
        ),
        3: meta(SymbolTypeName.PREDICATE, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
    }

    result = validate_tokens(
        [
            Token(symbol_id=1),
            Token(symbol_id=2),
            Token(symbol_id=3),
            Token(de_bruijn_index=0),
        ],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION


def test_prop_var_argument_consistency_constraint_is_not_applied() -> None:
    symbol_meta = {
        1: meta(SymbolTypeName.LOGICAL, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, 2),
        2: meta(SymbolTypeName.FREE_PROP_VAR, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, 1),
        3: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
        4: meta(SymbolTypeName.FREE_TERM_VAR, FormulaTypeName.TERM, None, 0),
    }

    result = validate_tokens(
        [
            Token(symbol_id=1),
            Token(symbol_id=2),
            Token(symbol_id=3),
            Token(symbol_id=2),
            Token(symbol_id=4),
        ],
        symbol_meta,
    )

    assert result == FormulaTypeName.PROPOSITION
