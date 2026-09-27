from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from dem.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthoringProvenance(Base):
    """Audit metadata for authored entities; never part of proof validation."""

    __tablename__ = "authoring_provenance"

    entity_kind: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_id: Mapped[str] = mapped_column(Text, primary_key=True)
    via: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    user_input: Mapped[str | None] = mapped_column(Text)
    accepted_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        default=utc_now,
    )
