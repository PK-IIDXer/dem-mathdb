"""Axiom-system-relative theorem queries on the public seed."""

from sqlalchemy.orm import Session

from dem.db.seed_labels import seed_axiom_system_name
from dem.services.axiom import AxiomService
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.types import AxiomStepInput


def _prove_axiom(session: Session, axiom_name: str, theorem_name: str):
    axioms = AxiomService(session)
    theorems = TheoremService(session)
    proofs = ProofService(session)
    axiom = axioms.get_by_name(axiom_name)
    theorem = theorems.register(theorem_name, axiom.formula_id)
    proof = proofs.create_proof(theorem.id)
    proofs.add_step(proof.id, AxiomStepInput(axiom.id), axiom.formula_id)
    proofs.validate(proof.id)
    return theorem, proof


def test_public_systems_distinguish_core_from_classical_axioms(
    seeded_session: Session,
) -> None:
    axioms = AxiomService(seeded_session)
    proofs = ProofService(seeded_session)
    core = axioms.get_system_by_name(seed_axiom_system_name("hilbert_core"))
    classical = axioms.get_system_by_name(seed_axiom_system_name("hilbert_classical"))

    core_theorem, core_proof = _prove_axiom(
        seeded_session, "hilbert_k", "test_core_axiom_instance"
    )
    classical_theorem, classical_proof = _prove_axiom(
        seeded_session, "hilbert_peirce", "test_classical_axiom_instance"
    )

    assert proofs.is_valid_in_system(core_proof.id, core.id)
    assert proofs.is_valid_in_system(core_proof.id, classical.id)
    assert not proofs.is_valid_in_system(classical_proof.id, core.id)
    assert proofs.is_valid_in_system(classical_proof.id, classical.id)

    assert [row.id for row in axioms.list_theorems_provable_in_system(core.id)] == [
        core_theorem.id
    ]
    assert {
        row.id for row in axioms.list_theorems_provable_in_system(classical.id)
    } == {core_theorem.id, classical_theorem.id}
