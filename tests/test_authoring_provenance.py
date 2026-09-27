"""Phase 2.8 authoring provenance contracts."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import AuthoringProvenance, Base
from dem.db.models.theorem import Proof, ProofStep
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds import seed_all
from dem.types import (
    LogicalDefinitionInput,
    PremiseStepInput,
    SymbolTypeName,
    Token,
)


def _migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20260910_0001_authoring_provenance.py"
    )
    spec = importlib.util.spec_from_file_location("authoring_provenance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        yield DemServices(session)
    engine.dispose()


def test_manual_authoring_records_entities_without_affecting_validation(dem):
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    symbol = dem.symbols.register("provenance_p", kind.id, 0)
    formula = dem.formulas.register([Token(symbol_id=symbol.id)])
    definition = dem.definitions.register(
        LogicalDefinitionInput(
            name="provenance_connective",
            param_symbol_ids=(symbol.id,),
            body_formula_id=formula.id,
        )
    )
    defining_formula_id = dem.definitions.get_axiom(definition.id).formula_id
    theorem = dem.theorems.register(
        "manual provenance theorem",
        formula.id,
        [formula.id],
    )
    proof = dem.proofs.create_proof(theorem.id)
    step = dem.proofs.add_step(proof.id, PremiseStepInput(0), formula.id)
    dem.proofs.validate(proof.id)

    rows = list(
        dem.session.scalars(
            select(AuthoringProvenance)
            .where(AuthoringProvenance.via == "manual")
            .order_by(
                AuthoringProvenance.entity_kind,
                AuthoringProvenance.entity_id,
            )
        )
    )
    assert {(row.entity_kind, row.entity_id) for row in rows} == {
        ("definition", str(definition.id)),
        ("formula", str(formula.id)),
        ("formula", str(defining_formula_id)),
        ("proof", str(proof.id)),
        ("proof_step", f"{proof.id}:{step.ord}"),
        ("theorem", str(theorem.id)),
    }
    assert all(row.provider is None and row.model is None for row in rows)
    assert dem.proofs.get(proof.id).status == "verified"
    assert dem.theorems.get(theorem.id).status == "proven"


def test_a_only_seed_has_no_generated_proof_provenance(seeded_session):
    proof_ids = set(seeded_session.scalars(select(Proof.id)))
    step_count = seeded_session.scalar(select(func.count()).select_from(ProofStep))
    rows = list(
        seeded_session.scalars(
            select(AuthoringProvenance).where(
                AuthoringProvenance.via == "seed"
            )
        )
    )

    assert proof_ids == set()
    assert step_count == 0
    assert rows == []

    seed_all(seeded_session)
    assert (
        seeded_session.scalar(
            select(func.count())
            .select_from(AuthoringProvenance)
            .where(AuthoringProvenance.via == "seed")
        )
        == 0
    )


def test_authoring_provenance_migration_up_and_down():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    change = _migration()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            change.upgrade()
            primary_key = inspect(connection).get_pk_constraint(
                "authoring_provenance"
            )
            assert primary_key["constrained_columns"] == [
                "entity_kind",
                "entity_id",
                "created_at",
            ]
            change.downgrade()
        assert "authoring_provenance" not in inspect(connection).get_table_names()
    engine.dispose()


def test_repeated_provenance_rows_in_one_second_get_distinct_microseconds(dem):
    dem.session.add_all(
        [
            AuthoringProvenance(entity_kind="formula", entity_id="same", via="manual"),
            AuthoringProvenance(entity_kind="formula", entity_id="same", via="manual"),
        ]
    )
    dem.session.flush()
    created = list(
        dem.session.scalars(
            select(AuthoringProvenance.created_at)
            .where(
                AuthoringProvenance.entity_kind == "formula",
                AuthoringProvenance.entity_id == "same",
            )
            .order_by(AuthoringProvenance.created_at)
        )
    )
    assert len(created) == 2
    assert created[0].replace(microsecond=0) == created[1].replace(microsecond=0)
    assert created[0].microsecond != created[1].microsecond
