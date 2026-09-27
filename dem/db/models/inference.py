from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dem.db.base import Base
from dem.db.models.language import Formula, Namespace
from dem.db.ordering import tag_name_order
from dem.identity import new_public_id

if TYPE_CHECKING:
    from dem.db.models.tag import Tag


class Axiom(Base):
    __tablename__ = "axiom"
    __table_args__ = (
        CheckConstraint(
            "origin_kind IN ('primitive', 'definition_derived')",
            name="known_origin_kind",
        ),
        CheckConstraint(
            "(origin_kind = 'primitive' AND definition_id IS NULL) "
            "OR (origin_kind = 'definition_derived' AND definition_id IS NOT NULL)",
            name="origin_definition_consistency",
        ),
        UniqueConstraint("definition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespace.id"), nullable=False)
    formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)
    origin_kind: Mapped[str] = mapped_column(Text, nullable=False)
    definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("definition.id", ondelete="CASCADE")
    )
    description: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    formula: Mapped[Formula] = relationship(lazy="joined")
    namespace: Mapped[Namespace] = relationship(lazy="joined")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="axiom_tag",
        lazy="selectin",
        viewonly=True,
        order_by=tag_name_order,
    )


class AxiomSystem(Base):
    __tablename__ = "axiom_system"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    members: Mapped[list[AxiomSystemMember]] = relationship(
        back_populates="axiom_system",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class AxiomSystemMember(Base):
    __tablename__ = "axiom_system_member"

    axiom_system_id: Mapped[int] = mapped_column(
        ForeignKey("axiom_system.id", ondelete="CASCADE"), primary_key=True
    )
    axiom_id: Mapped[int] = mapped_column(
        ForeignKey("axiom.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    axiom_system: Mapped[AxiomSystem] = relationship(back_populates="members")
    axiom: Mapped[Axiom] = relationship(lazy="joined")


class InferenceRule(Base):
    __tablename__ = "inference_rule"
    __table_args__ = (
        # Only the two primitive rules and implication introduction are public.
        # The public candidate has zero source-specific `inference_rule.kind`
        # values; validation remains enforced by the same database constraint.
        # §7.1's proof generator.
        CheckConstraint(
            "kind IN ('modus_ponens', 'generalization', 'implication_intro')",
            name="known_kind",
        ),
        CheckConstraint("premise_count >= 0", name="premise_count_nonnegative"),
        # Design doc §9.5: what justifies the rule, which is also what it costs
        # to remove it. `recognizer` is the forbidden tier and no rule sits at it
        # any more; the CHECK still names it so that adding one stays a visible,
        # deliberate act rather than an ordinary new row.
        CheckConstraint(
            "tier IN ('primitive', 'derived', 'admissible', 'recognizer')",
            name="known_tier",
        ),
        # An admissible rule shrinks premise_deps or carries an eigenvariable
        # condition, so it is justified by a whole-proof transformation rather
        # than a schematic derivation. Naming that transformation is the price
        # of admitting one; nothing else may claim to have it.
        CheckConstraint(
            "(tier = 'admissible') = (elimination_procedure IS NOT NULL)",
            name="admissible_requires_elimination_procedure",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    elimination_procedure: Mapped[str | None] = mapped_column(Text)
    premise_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_variable_param: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
