from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select

from dem.api import DemApi, DemServices
from dem.db.models.definition import Definition
from dem.db.models.language import Symbol
from dem.errors import NotFoundError
from dem.types import LogicalDefinitionInput, SymbolTypeName, Token


def make_api() -> DemApi:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    return DemApi(engine)


def test_initialize_database_creates_schema_and_seed_data() -> None:
    api = make_api()
    api.initialize_database()

    with api.session() as dem:
        assert isinstance(dem, DemServices)
        assert dem.symbols.get_by_role("implication").id > 0
        assert dem.symbols.get_by_role("universal_quantifier").id > 0
        assert dem.proofs.get_inference_rule_by_name("MP").kind == "modus_ponens"
        assert dem.proofs.get_inference_rule_by_name("Gen").kind == "generalization"
        assert dem.axioms.get_by_name("hilbert_k").id > 0


def test_transaction_commits_successful_service_work() -> None:
    api = make_api()
    api.initialize_database()

    with api.transaction() as dem:
        term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
        dem.symbols.register("api_x", term_type.id, 0)

    with api.session() as dem:
        assert dem.symbols.get_by_name("api_x").name == "api_x"


def test_transaction_rolls_back_on_exception() -> None:
    api = make_api()
    api.initialize_database()

    with pytest.raises(RuntimeError, match="boom"):
        with api.transaction() as dem:
            term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
            dem.symbols.register("rolled_back_x", term_type.id, 0)
            raise RuntimeError("boom")

    with api.session() as dem:
        with pytest.raises(NotFoundError):
            dem.symbols.get_by_name("rolled_back_x")


def test_failed_definition_registration_rolls_back_symbol_and_definition() -> None:
    api = make_api()
    api.initialize_database()

    with api.session() as dem:
        before = {
            model: dem.session.scalar(select(func.count()).select_from(model))
            for model in (Symbol, Definition)
        }

    with pytest.raises(RuntimeError, match="late definition failure"):
        with api.transaction() as dem:
            prop_type = dem.symbols.get_symbol_type_by_name(
                SymbolTypeName.FREE_PROP_VAR.value
            )
            phi = dem.symbols.register("rollback_phi", prop_type.id, 0)
            body = dem.formulas.register([Token(symbol_id=phi.id)])
            with patch.object(
                dem.definitions._formula_svc,
                "register",
                side_effect=RuntimeError("late definition failure"),
            ):
                dem.definitions.register(
                    LogicalDefinitionInput(
                        name="rolled_back_definition",
                        param_symbol_ids=(phi.id,),
                        body_formula_id=body.id,
                        latex_template=r"\mathsf{RolledBack}",
                    )
                )

    with api.session() as dem:
        after = {
            model: dem.session.scalar(select(func.count()).select_from(model))
            for model in (Symbol, Definition)
        }
        assert after == before
        with pytest.raises(NotFoundError):
            dem.symbols.get_by_name("rolled_back_definition")


def test_from_url_builds_working_api_boundary() -> None:
    api = DemApi.from_url("sqlite+pysqlite:///:memory:")
    api.initialize_database(seed=False)

    with api.transaction() as dem:
        assert dem.symbols.list_formula_types() == []
