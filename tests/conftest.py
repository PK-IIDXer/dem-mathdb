"""A-only public test fixtures.

The public seed is intentionally small, so tests build isolated in-memory
databases instead of carrying snapshots derived from excluded content.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from dem.api import DemApi
from dem.db.models import Base
from dem.db.seeds import seed_all
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    AxiomStepInput,
    PremiseStepInput,
    PropSubst,
    Substitution,
    TermSubst,
    TheoremStepInput,
    Token,
)


def _public_session(path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_all(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def seeded_session(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    yield from _public_session(tmp_path_factory.mktemp("seeded") / "seeded.db")


@pytest.fixture
def fresh_seeded_session(tmp_path: Path) -> Iterator[Session]:
    yield from _public_session(tmp_path / "fresh-seeded.db")


@pytest.fixture(scope="module")
def all_seeded_session(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    yield from _public_session(tmp_path_factory.mktemp("public-seed") / "all.db")


@pytest.fixture
def l2_seeded_session(tmp_path: Path) -> Iterator[Session]:
    """Compatibility name for generic tests; contains only the public seed."""
    yield from _public_session(tmp_path / "compat-public.db")


class PublicSchemaOrigins:
    def __init__(self, root: Path) -> None:
        self.root = root

    @contextmanager
    def l2_origin_urls(self, database: str):
        if database != "sqlite":
            pytest.skip("public schema-origin fixture currently covers SQLite")
        migration = self.root / "alembic.db"
        model = self.root / "create-all.db"
        migration_url = f"sqlite+pysqlite:///{migration.as_posix()}"
        model_url = f"sqlite+pysqlite:///{model.as_posix()}"

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", migration_url)
        command.upgrade(config, "head")

        migration_api = DemApi.from_url(migration_url)
        model_api = DemApi.from_url(model_url)
        model_api.create_schema()
        try:
            with migration_api.transaction() as dem:
                seed_all(dem.session)
                _add_schema_fixture_proofs(dem.session)
            with model_api.transaction() as dem:
                seed_all(dem.session)
                _add_schema_fixture_proofs(dem.session)
            yield migration_url, model_url
        finally:
            migration_api.engine.dispose()
            model_api.engine.dispose()


@pytest.fixture
def seed_snapshot_factory(tmp_path: Path) -> PublicSchemaOrigins:
    return PublicSchemaOrigins(tmp_path)


def _add_schema_fixture_proofs(session: Session) -> None:
    """Add two test-only verified proofs for trigger mutation matrices."""
    axioms = AxiomService(session)
    formulas = FormulaService(session)
    symbols = SymbolService(session)
    theorems = TheoremService(session)
    proofs = ProofService(session)
    for axiom_name in ("hilbert_k", "hilbert_s"):
        axiom = axioms.get_by_name(axiom_name)
        theorem = theorems.register(f"schema_fixture_{axiom_name}", axiom.formula_id)
        proof = proofs.create_proof(theorem.id)
        proofs.add_step(proof.id, AxiomStepInput(axiom.id), axiom.formula_id)
        proofs.validate(proof.id)
    premise_formula = axioms.get_by_name("hilbert_k").formula_id
    premise_theorem = theorems.register(
        "schema_fixture_premise", premise_formula, [premise_formula]
    )
    premise_proof = proofs.create_proof(premise_theorem.id)
    proofs.add_step(premise_proof.id, PremiseStepInput(0), premise_formula)
    proofs.validate(premise_proof.id)

    phi1 = symbols.get_by_name("φ¹")
    t = symbols.get_by_name("t")
    x = symbols.get_by_name("x")
    equality = symbols.get_by_role("equality")
    schema = formulas.register(
        [Token(symbol_id=equality.id), Token(symbol_id=x.id), Token(symbol_id=x.id)]
    )
    x_formula = formulas.register([Token(symbol_id=x.id)])
    forall_elim = axioms.get_by_name("hilbert_forall_elim")
    substitution = Substitution(
        term_substs=(TermSubst(t.id, x_formula.id),),
        prop_substs=(PropSubst(phi1.id, schema.id, (x.id,)),),
    )
    instantiated = formulas.register(
        proofs.compute_substituted_tokens(forall_elim.formula_id, substitution)
    )
    substitution_theorem = theorems.register(
        "schema_fixture_substitution", instantiated.id
    )
    substitution_proof = proofs.create_proof(substitution_theorem.id)
    proofs.add_step(
        substitution_proof.id,
        AxiomStepInput(forall_elim.id, substitution),
        instantiated.id,
    )
    proofs.validate(substitution_proof.id)

    applied_theorem = theorems.register(
        "schema_fixture_applied", premise_formula, [premise_formula]
    )
    applied_proof = proofs.create_proof(applied_theorem.id)
    proofs.add_step(applied_proof.id, PremiseStepInput(0), premise_formula)
    proofs.add_step(
        applied_proof.id,
        TheoremStepInput(premise_proof.id, Substitution(), (0,)),
        premise_formula,
    )
    proofs.validate(applied_proof.id)
