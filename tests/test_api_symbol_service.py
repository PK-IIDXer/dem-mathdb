from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete, func, select

from dem.api import DemApi
from dem.db.models.language import FormulaToken, SymbolRole
from dem.errors import ConflictError, NotFoundError, ValidationError
from dem.types import FormulaTypeName, SymbolTypeName, Token


def make_api() -> DemApi:
    api = DemApi(create_engine("sqlite+pysqlite:///:memory:"))
    api.initialize_database()
    return api


def test_formula_type_and_symbol_type_read_api() -> None:
    api = make_api()

    with api.session() as dem:
        formula_types = dem.symbols.list_formula_types()
        symbol_types = dem.symbols.list_symbol_types()

        assert [item.name for item in formula_types] == [
            FormulaTypeName.TERM.value,
            FormulaTypeName.PROPOSITION.value,
        ]
        assert [item.name for item in symbol_types] == [
            SymbolTypeName.FUNCTION.value,
            SymbolTypeName.PREDICATE.value,
            SymbolTypeName.LOGICAL.value,
            SymbolTypeName.QUANT_PROP.value,
            SymbolTypeName.QUANT_TERM.value,
            SymbolTypeName.FREE_TERM_VAR.value,
            SymbolTypeName.FREE_PROP_VAR.value,
        ]
        assert dem.symbols.get_formula_type(formula_types[0].id).name == FormulaTypeName.TERM.value
        assert dem.symbols.get_formula_type_by_name(FormulaTypeName.PROPOSITION.value).id == formula_types[1].id
        assert dem.symbols.get_symbol_type(symbol_types[0].id).name == SymbolTypeName.FUNCTION.value
        assert dem.symbols.get_symbol_type_by_name(SymbolTypeName.LOGICAL.value).id == symbol_types[2].id


def test_register_get_and_list_symbols_by_type_through_api_context() -> None:
    api = make_api()

    with api.transaction() as dem:
        term_var_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        x = dem.symbols.register("api_symbol_x", term_var_type.id, 0, remarks="api symbol")

    with api.session() as dem:
        term_var_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        by_id = dem.symbols.get(x.id)
        by_name = dem.symbols.get_by_name("api_symbol_x")
        names = [symbol.name for symbol in dem.symbols.list_by_type(term_var_type.id)]

        assert by_id.id == by_name.id
        assert by_name.remarks == "api symbol"
        assert "api_symbol_x" in names


def test_symbol_registration_validation_matches_api_spec() -> None:
    api = make_api()

    with api.transaction() as dem:
        quant_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.QUANT_PROP.value)
        term_var_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        dem.symbols.register("dup_symbol", term_var_type.id, 0)

        with pytest.raises(NotFoundError, match="SymbolType"):
            dem.symbols.register("missing_type", 999999, 0)

        with pytest.raises(ValidationError, match="arity must be >= 0"):
            dem.symbols.register("negative_arity", term_var_type.id, -1)

        with pytest.raises(ValidationError, match="arity must be 1"):
            dem.symbols.register("bad_quant_arity", quant_type.id, 2)

        with pytest.raises(ConflictError, match="Symbol.name"):
            dem.symbols.register("dup_symbol", term_var_type.id, 0)


def test_symbol_aliases_are_unique_across_aliases_and_symbol_names() -> None:
    api = make_api()

    with api.transaction() as dem:
        term_var_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        variable = dem.symbols.register("alias_target", term_var_type.id, 0)
        alias = dem.symbols.add_alias(variable.id, "friendly")
        assert dem.symbols.add_alias(variable.id, "friendly").id == alias.id

        with pytest.raises(ConflictError) as alias_collision:
            dem.symbols.add_alias(variable.id, "∀")
        assert alias_collision.value.code == "symbol.alias_collision"

        with pytest.raises(ConflictError) as name_collision:
            dem.symbols.register("friendly", term_var_type.id, 0)
        assert name_collision.value.code == "symbol.alias_collision"


def test_symbol_read_api_not_found_errors() -> None:
    api = make_api()

    with api.session() as dem:
        with pytest.raises(NotFoundError, match="FormulaType"):
            dem.symbols.get_formula_type(999999)
        with pytest.raises(NotFoundError, match="FormulaType"):
            dem.symbols.get_formula_type_by_name("missing_formula_type")
        with pytest.raises(NotFoundError, match="SymbolType"):
            dem.symbols.get_symbol_type(999999)
        with pytest.raises(NotFoundError, match="SymbolType"):
            dem.symbols.get_symbol_type_by_name("missing_symbol_type")
        with pytest.raises(NotFoundError, match="Symbol"):
            dem.symbols.get(999999)
        with pytest.raises(NotFoundError, match="Symbol"):
            dem.symbols.get_by_name("missing_symbol")


def test_symbol_lookup_does_not_translate_legacy_seed_variable_names() -> None:
    api = make_api()
    with api.transaction() as dem:
        assert dem.symbols.get_by_name("t").symbol_type.name == SymbolTypeName.FREE_TERM_VAR.value
        with pytest.raises(NotFoundError):
            dem.symbols.get_by_name("f")
        with pytest.raises(NotFoundError, match="SymbolType"):
            dem.symbols.list_by_type(999999)


def test_formula_registration_and_usage_recalculation_agree() -> None:
    api = make_api()
    with api.transaction() as dem:
        term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        function_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FUNCTION.value)
        term = dem.symbols.register("usage_term", term_type.id, 0)
        pair = dem.symbols.register("usage_pair", function_type.id, 2)
        tokens = [
            Token(symbol_id=pair.id),
            Token(symbol_id=term.id),
            Token(symbol_id=term.id),
        ]

        formula = dem.formulas.register(tokens)
        assert dem.formulas.register(tokens).id == formula.id
        counts = {
            symbol.id: count for symbol, count in dem.symbols.list_with_usage()
        }
        assert counts[pair.id] == 1
        assert counts[term.id] == 1

        dem.formulas.register([Token(symbol_id=term.id)])

    with api.session() as dem:
        counts = {
            symbol.id: count for symbol, count in dem.symbols.list_with_usage()
        }
        assert counts[pair.id] == 1
        assert counts[term.id] == 2

    with api.transaction() as dem:
        pair = dem.symbols.get_by_name("usage_pair")
        term = dem.symbols.get_by_name("usage_term")
        pair.usage_count = 99
        term.usage_count = 99
        dem.session.flush()
        dem.symbols.recalculate_usage_counts()
        counts = {
            symbol.id: count for symbol, count in dem.symbols.list_with_usage()
        }
        assert counts[pair.id] == 1
        assert counts[term.id] == 2


def test_formula_usage_count_discards_rolled_back_registration() -> None:
    api = make_api()
    with api.transaction() as dem:
        term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        term = dem.symbols.register("rolled_back_usage_term", term_type.id, 0)
        term_id = term.id

    with api.session() as dem:
        dem.formulas.register([Token(symbol_id=term_id)])
        dem.session.rollback()

        term = dem.symbols.get(term_id)
        assert term.usage_count == 0
        actual = dem.session.scalar(
            select(func.count(func.distinct(FormulaToken.formula_id))).where(
                FormulaToken.symbol_id == term_id
            )
        )
        assert actual == 0


def test_formula_usage_count_preserves_outer_delta_across_savepoint_rollback() -> None:
    api = make_api()
    with api.transaction() as dem:
        term_type = dem.symbols.get_symbol_type_by_name(
            SymbolTypeName.FREE_TERM_VAR.value
        )
        outer_symbol = dem.symbols.register(
            "savepoint_outer_usage_term", term_type.id, 0
        )
        nested_symbol = dem.symbols.register(
            "savepoint_nested_usage_term", term_type.id, 0
        )
        outer_symbol_id = outer_symbol.id
        nested_symbol_id = nested_symbol.id

    with api.session() as dem:
        dem.formulas.register([Token(symbol_id=outer_symbol_id)])
        savepoint = dem.session.begin_nested()
        dem.formulas.register([Token(symbol_id=nested_symbol_id)])
        savepoint.rollback()
        dem.session.commit()

    with api.session() as dem:
        stored = {
            symbol.id: count for symbol, count in dem.symbols.list_with_usage()
        }
        actual = {
            symbol_id: dem.session.scalar(
                select(func.count(func.distinct(FormulaToken.formula_id))).where(
                    FormulaToken.symbol_id == symbol_id
                )
            )
            for symbol_id in (outer_symbol_id, nested_symbol_id)
        }

    assert stored[outer_symbol_id] == actual[outer_symbol_id] == 1
    assert stored[nested_symbol_id] == actual[nested_symbol_id] == 0


def test_symbol_role_read_and_assignment_validation() -> None:
    api = make_api()

    with api.session() as dem:
        assert dem.symbols.get_by_role("implication").symbol_type.name == SymbolTypeName.LOGICAL.value

        with pytest.raises(ValidationError, match="unknown role"):
            dem.symbols.get_by_role("missing_role")

    with api.transaction() as dem:
        logical_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.LOGICAL.value)
        predicate_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.PREDICATE.value)
        new_imp = dem.symbols.register("new_implication_like", logical_type.id, 2)
        bad_imp = dem.symbols.register("bad_implication_like", predicate_type.id, 2)

        dem.session.execute(delete(SymbolRole).where(SymbolRole.role == "implication"))
        dem.symbols.assign_role("implication", new_imp.id)

        with pytest.raises(ValidationError, match="unknown role"):
            dem.symbols.assign_role("missing_role", new_imp.id)

        with pytest.raises(NotFoundError, match="Symbol"):
            dem.symbols.assign_role("universal_quantifier", 999999)

        with pytest.raises(ValidationError, match="requires"):
            dem.symbols.assign_role("universal_quantifier", bad_imp.id)

        with pytest.raises(ConflictError, match="SymbolRole.role"):
            dem.symbols.assign_role("implication", new_imp.id)

        dem.session.execute(delete(SymbolRole).where(SymbolRole.role == "biconditional"))
        with pytest.raises(ConflictError, match="SymbolRole.symbol_id"):
            dem.symbols.assign_role("biconditional", new_imp.id)
