"""Read-only corpus counts for the selected workspace."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from dem.api import DemServices
from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom, AxiomSystem
from dem.db.models.theorem import Proof, ProofStep, Theorem
from webapi.presentation import visible_theorems
from webapi.deps import dem_services

router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats(dem: DemServices = Depends(dem_services, scope="function")) -> dict[str, int]:
    """Steps include all proofs of visible theorems, regardless of proof status.

    Dependencies count distinct (citing theorem, cited theorem) pairs across
    those proofs, not steps or proof pairs. Self references are not dependencies
    on another theorem.
    """
    session = dem.session
    visible = select(Theorem.id).where(visible_theorems())
    visible_proofs = select(Proof.id).where(Proof.theorem_id.in_(visible))
    cited = aliased(Proof)
    pairs = (
        select(Proof.theorem_id, cited.theorem_id.label("cited_theorem_id"))
        .select_from(ProofStep)
        .join(Proof, Proof.id == ProofStep.proof_id)
        .join(cited, cited.id == ProofStep.applied_proof_id)
        .where(
            Proof.theorem_id.in_(visible),
            cited.theorem_id.in_(visible),
            ProofStep.step_kind == "theorem",
            Proof.theorem_id != cited.theorem_id,
        )
        .distinct()
        .subquery()
    )

    def count(model, *conditions):
        return session.scalar(select(func.count()).select_from(model).where(*conditions))

    return {
        "theorem_count": count(Theorem, Theorem.id.in_(visible)),
        "proven_theorem_count": count(Theorem, Theorem.id.in_(visible), Theorem.status == "proven"),
        "verified_proof_count": count(Proof, Proof.id.in_(visible_proofs), Proof.status == "verified"),
        "proof_step_count": count(ProofStep, ProofStep.proof_id.in_(visible_proofs)),
        "axiom_count": count(Axiom),
        "primitive_axiom_count": count(Axiom, Axiom.origin_kind == "primitive"),
        "axiom_system_count": count(AxiomSystem),
        "definition_count": count(Definition),
        "dependency_count": count(pairs),
    }
