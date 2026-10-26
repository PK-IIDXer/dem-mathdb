"""Independent public demonstrations retain real proof and package validation."""
import pytest
from sqlalchemy import select
from dem.db.models import Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof
from dem.db.seeds import seed_all
from dem.db.seeds.public_demo import DEMO_NAMES
from dem.services.proof import ProofService
from dem.services.axiom import AxiomService
from dem.services.theorem import TheoremService
from scripts.beta_base import publish_all, verify

SEED_PHASE = "public_demo"


def test_public_entities_and_real_verified_proofs(fresh_seeded_session):
    session = fresh_seeded_session
    for model in (Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof):
        rows = list(session.scalars(select(model)))
        assert rows and all(row.release_id is not None for row in rows)
    definition = session.scalar(select(Definition))
    assert definition.name == "同式含意"
    assert session.scalar(select(Symbol.name).where(Symbol.id == definition.new_symbol_id)) == "同式含意"
    assert session.scalar(select(Axiom.name).where(Axiom.definition_id == definition.id)) == "同式含意 定義公理"
    theorems = list(session.scalars(select(Theorem)))
    proofs = list(session.scalars(select(Proof)))
    assert len(theorems) == 5 and all(t.status == "proven" for t in theorems)
    assert len(proofs) == 6 and all(p.status == "verified" for p in proofs)
    seed_all(session)
    assert len(list(session.scalars(select(Proof)))) == 6


@pytest.mark.parametrize("name", DEMO_NAMES)
def test_demo_axiom_system_validity(fresh_seeded_session, name):
    session = fresh_seeded_session
    service = ProofService(session)
    theorem = TheoremService(session).get_by_name(name)
    systems = AxiomService(session)
    for proof in service.list_for_theorem(theorem.id):
        assert proof.status == "verified"
        assert service.is_valid_in_system(proof.id, systems.get_system_by_name("hilbert_classical").id)
        assert service.is_valid_in_system(proof.id, systems.get_system_by_name("hilbert_core").id) == (name != "古典含意の例")


def test_public_package_catalog_is_complete(base_api):
    publish_all(base_api.engine)
    result = verify(base_api.engine)
    assert result["ok"], result


from beta2_support import base_api


def test_fixture_schema_setup_preserves_existing_loggers(tmp_path, caplog, monkeypatch):
    import logging
    from sqlalchemy.engine import make_url
    from conftest import _upgrade_schema
    logger = logging.getLogger("public.fixture.audit")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "level", logging.WARNING)
    _upgrade_schema(make_url("sqlite+pysqlite:///" + (tmp_path / "logging.db").as_posix()))
    assert logger.disabled is False
    logger.warning("fixture-audit-remains-visible")
    assert "fixture-audit-remains-visible" in caplog.text
