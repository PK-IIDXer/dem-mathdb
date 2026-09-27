"""`GET /proofs/{id}/direct-dependencies` -- the one-hop read the dependency tree needs.

The theorem page's dependency tree used to derive each lemma's name from the
steps, one `GET /proofs/{id}` per applied proof and one `GET /theorems/{id}`
per lemma. This endpoint answers the same question once; the tests check it
agrees with that per-step derivation.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models.theorem import Proof
from dem.types import AxiomStepInput
from dem.errors import NotFoundError
from webapi.routers.proofs import list_direct_dependencies, list_proof_steps

SEED_PHASE = "l2"


def test_matches_the_per_step_derivation(seeded_session: Session) -> None:
    dem = DemServices(seeded_session)
    axiom = dem.axioms.get_by_name("hilbert_k")
    theorem = dem.theorems.register("direct_dependency_probe", axiom.formula_id)
    proof = dem.proofs.create_proof(theorem.id)
    dem.proofs.add_step(proof.id, AxiomStepInput(axiom.id), axiom.formula_id)
    dem.proofs.validate(proof.id)
    proof_id = proof.id
    steps = list_proof_steps(proof_id, dem)

    result = list_direct_dependencies(proof_id, dem)

    wanted_axiom_ids = list(
        dict.fromkeys(step.axiom.id for step in steps if step.step_kind == "axiom")
    )
    assert [axiom.id for axiom in result.axioms] == wanted_axiom_ids

    wanted_theorem_ids = list(
        dict.fromkeys(
            dem.proofs.get(step.applied_proof_id).theorem_id
            for step in steps
            if step.step_kind == "theorem"
        )
    )
    assert [lemma.theorem.id for lemma in result.lemmas] == wanted_theorem_ids
    assert wanted_theorem_ids == []

    applied_proof_ids = {step.applied_proof_id for step in steps if step.step_kind == "theorem"}
    assert set(result.applied_proofs) == applied_proof_ids
    for lemma in result.lemmas:
        assert lemma.proof_id in applied_proof_ids
        applied = dem.proofs.get(lemma.proof_id)
        assert applied.theorem_id == lemma.theorem.id
        assert applied.status == "verified"
        assert lemma.theorem.name == dem.theorems.get(lemma.theorem.id).name


def test_reports_an_unknown_proof(seeded_session: Session) -> None:
    """Without the existence check this would return empty lists, not a 404."""
    dem = DemServices(seeded_session)
    missing = (seeded_session.scalar(select(func.max(Proof.id))) or 0) + 1

    with pytest.raises(NotFoundError):
        list_direct_dependencies(missing, dem)
