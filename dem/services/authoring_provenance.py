from __future__ import annotations

from typing import Literal, TypeAlias

from sqlalchemy.orm import Session

from dem.db.models.authoring_provenance import AuthoringProvenance


AuthoringVia: TypeAlias = Literal["manual", "seed"]


def record_authoring_provenance(
    session: Session,
    *,
    entity_kind: str,
    entity_id: str | int,
    via: AuthoringVia | None,
) -> None:
    """Record Phase 2 provenance without coupling it to validation."""
    if via is None:
        return
    session.add(
        AuthoringProvenance(
            entity_kind=entity_kind,
            entity_id=str(entity_id),
            via=via,
        )
    )
