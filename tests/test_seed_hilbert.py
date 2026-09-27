from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.models.inference import Axiom, AxiomSystem
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seed_labels import seed_axiom_name, seed_axiom_system_name
from dem.db.seeds.hilbert import (
    HILBERT_CLASSICAL_AXIOM_NAMES,
    HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME,
    HILBERT_CORE_AXIOM_NAMES,
    HILBERT_CORE_AXIOM_SYSTEM_NAME,
    seed_hilbert_core,
)
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import AxiomStepInput, MPStepInput, PropSubst, Substitution, Token


@pytest.fixture(scope="module")
def seeded_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    seed_hilbert_core(session)
    yield session
    session.close()


def test_seed_hilbert_core_registers_axioms_and_systems_idempotently(seeded_session: Session) -> None:
    session = seeded_session
    axiom_count = session.scalar(select(func.count()).select_from(Axiom))
    system_count = session.scalar(select(func.count()).select_from(AxiomSystem))

    summary = seed_hilbert_core(session)

    assert summary.core_axiom_names == HILBERT_CORE_AXIOM_NAMES
    assert summary.classical_axiom_names == HILBERT_CLASSICAL_AXIOM_NAMES
    assert session.scalar(select(func.count()).select_from(Axiom)) == axiom_count
    assert session.scalar(select(func.count()).select_from(AxiomSystem)) == system_count
    assert _system(session, seed_axiom_system_name(HILBERT_CORE_AXIOM_SYSTEM_NAME)) is not None
    assert _system(session, seed_axiom_system_name(HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME)) is not None


def test_hilbert_k_and_s_seed_can_prove_phi_implies_phi(seeded_session: Session) -> None:
    session = seeded_session
    symbols = SymbolService(session)
    formulas = FormulaService(session)
    axioms = AxiomService(session)
    theorems = TheoremService(session)
    proofs = ProofService(session)

    imp = symbols.get_by_role("implication")
    phi = symbols.get_by_name("φ")
    psi = symbols.get_by_name("ψ")
    chi = symbols.get_by_name("χ")

    phi_formula = formulas.register([Token(symbol_id=phi.id)])
    phi_to_phi = formulas.register(
        [Token(symbol_id=imp.id), Token(symbol_id=phi.id), Token(symbol_id=phi.id)]
    )
    k_axiom = axioms.get_by_name("hilbert_k")
    s_axiom = axioms.get_by_name("hilbert_s")
    theorem = theorems.register("seeded_hilbert_phi_to_phi", phi_to_phi.id)
    proof = proofs.create_proof(theorem.id)

    sigma0 = Substitution(
        prop_substs=(
            PropSubst(psi.id, phi_to_phi.id),
            PropSubst(chi.id, phi_formula.id),
        )
    )
    step0 = formulas.register(proofs.compute_substituted_tokens(s_axiom.formula_id, sigma0))
    proofs.add_step(proof.id, AxiomStepInput(s_axiom.id, sigma0), step0.id)

    sigma1 = Substitution(prop_substs=(PropSubst(psi.id, phi_to_phi.id),))
    step1 = formulas.register(proofs.compute_substituted_tokens(k_axiom.formula_id, sigma1))
    proofs.add_step(proof.id, AxiomStepInput(k_axiom.id, sigma1), step1.id)

    step2 = formulas.register(
        [
            Token(symbol_id=imp.id),
            Token(symbol_id=imp.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=imp.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=imp.id),
            Token(symbol_id=phi.id),
            Token(symbol_id=phi.id),
        ]
    )
    proofs.add_step(proof.id, MPStepInput(1, 0), step2.id)

    sigma3 = Substitution(prop_substs=(PropSubst(psi.id, phi_formula.id),))
    step3 = formulas.register(proofs.compute_substituted_tokens(k_axiom.formula_id, sigma3))
    proofs.add_step(proof.id, AxiomStepInput(k_axiom.id, sigma3), step3.id)

    proofs.add_step(proof.id, MPStepInput(3, 2), phi_to_phi.id)
    proofs.validate(proof.id)

    assert proofs.get(proof.id).status == "verified"
    assert theorems.get(theorem.id).status == "proven"
    assert [axiom.name for axiom in proofs.list_used_axioms(proof.id)] == [
        seed_axiom_name("hilbert_k"),
        seed_axiom_name("hilbert_s"),
    ]


def _system(session: Session, name: str) -> AxiomSystem | None:
    return session.scalar(select(AxiomSystem).where(AxiomSystem.name == name))
