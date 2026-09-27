from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dem.db.base import Base
from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom
from dem.db.models.theorem import Theorem


class Tag(Base):
    """A free-form label (for example a field or an ad hoc topic)
    attachable to axioms/theorems/definitions for search and
    filtering. Intentionally flat: "field" is a usage convention, not a
    separate schema concept."""

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AxiomTag(Base):
    __tablename__ = "axiom_tag"

    axiom_id: Mapped[int] = mapped_column(ForeignKey("axiom.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    axiom: Mapped[Axiom] = relationship(lazy="joined")
    tag: Mapped[Tag] = relationship(lazy="joined")


class TheoremTag(Base):
    __tablename__ = "theorem_tag"

    theorem_id: Mapped[int] = mapped_column(
        ForeignKey("theorem.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    theorem: Mapped[Theorem] = relationship(lazy="joined")
    tag: Mapped[Tag] = relationship(lazy="joined")


class DefinitionTag(Base):
    __tablename__ = "definition_tag"

    definition_id: Mapped[int] = mapped_column(
        ForeignKey("definition.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    definition: Mapped[Definition] = relationship(lazy="joined")
    tag: Mapped[Tag] = relationship(lazy="joined")
