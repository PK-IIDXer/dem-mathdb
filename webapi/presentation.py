"""Display-only filtering. Never use these predicates in proof validation."""
from sqlalchemy import select
from dem.db.models.theorem import Theorem
from dem.services.system_tags import HIDDEN_THEOREM_TAGS, visible_theorem_clause


def visible_theorems():
    return visible_theorem_clause(Theorem.id, HIDDEN_THEOREM_TAGS)


def visible_ids(session, ids):
    return set(session.scalars(select(Theorem.id).where(Theorem.id.in_(ids), visible_theorems()))) if ids else set()


def displayed(session, theorems):
    items = list(theorems)
    ids = visible_ids(session, [item.id for item in items])
    return [item for item in items if item.id in ids]
