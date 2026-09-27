"""Names shown for a proposition are exact stored formula matches."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models.inference import Axiom
from dem.db.models.theorem import Theorem
from dem.errors import NotFoundError
from webapi.routers.formulas import named_conclusions
from webapi.schemas import NamedConclusionsOut

SEED_PHASE = "l0"


def test_named_conclusions_match_exact_formula_id(seeded_session: Session) -> None:
    formula_id = seeded_session.scalar(select(Axiom.formula_id).limit(1))
    assert formula_id is not None
    result = named_conclusions(formula_id, DemServices(seeded_session))
    assert isinstance(result, NamedConclusionsOut)
    assert {item.public_id for item in result.axioms} == set(seeded_session.scalars(
        select(Axiom.public_id).where(Axiom.formula_id == formula_id)
    ))
    assert {item.public_id for item in result.theorems} == set(seeded_session.scalars(
        select(Theorem.public_id).where(Theorem.conclusion_formula_id == formula_id)
    ))
    assert result.axioms


def test_named_conclusions_reject_unknown_formula(seeded_session: Session) -> None:
    missing = (seeded_session.scalar(select(func.max(Axiom.formula_id))) or 0) + 1000000
    with pytest.raises(NotFoundError):
        named_conclusions(missing, DemServices(seeded_session))
