from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.db.models.inference import Axiom
from dem.db.models.theorem import Proof, Theorem
from dem.db.seed_labels import seed_axiom_name, seed_theorem_name


def axioms_exist(session: Session, names: Iterable[str]) -> bool:
    expected = {seed_axiom_name(name) for name in names}
    if not expected:
        return True
    count = session.scalar(
        select(func.count()).select_from(Axiom).where(Axiom.name.in_(expected))
    )
    return count == len(expected)


def theorems_are_proven(session: Session, names: Iterable[str]) -> bool:
    expected = {seed_theorem_name(name) for name in names}
    if not expected:
        return True
    count = session.scalar(
        select(func.count(func.distinct(Theorem.id)))
        .select_from(Theorem)
        .join(Proof, Proof.theorem_id == Theorem.id)
        .where(Theorem.name.in_(expected), Theorem.status == "proven")
        .where(Proof.status == "verified")
    )
    return count == len(expected)
