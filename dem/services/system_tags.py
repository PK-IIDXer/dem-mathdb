from __future__ import annotations

from sqlalchemy import exists, select

from dem.db.models.tag import Tag, TheoremTag


ONBOARDING_TAG = "system:onboarding"
EXPLORATION_TAG = "system:exploration"
HIDDEN_THEOREM_TAGS = frozenset({ONBOARDING_TAG, EXPLORATION_TAG})
EXPLORATION_THEOREM_TAGS = frozenset({EXPLORATION_TAG})


def visible_theorem_clause(theorem_id, hidden_tags=EXPLORATION_THEOREM_TAGS):
    """SQL predicate for ordinary theorem lists and discovery surfaces."""
    theorem_tag = TheoremTag.__table__.alias("hidden_theorem_tag")
    tag = Tag.__table__.alias("hidden_theorem_tag_name")
    hidden = (
        select(theorem_tag.c.theorem_id)
        .select_from(theorem_tag.join(tag, tag.c.id == theorem_tag.c.tag_id))
        .where(
            theorem_tag.c.theorem_id == theorem_id,
            tag.c.name.in_(hidden_tags),
        )
    )
    return ~exists(hidden)
