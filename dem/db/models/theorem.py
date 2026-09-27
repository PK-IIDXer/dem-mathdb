from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dem.db.base import Base
from dem.db.models.inference import Axiom, InferenceRule
from dem.db.models.language import Formula, Namespace
from dem.db.ordering import tag_name_order
from dem.identity import new_public_id

if TYPE_CHECKING:
    from dem.db.models.tag import Tag


class Theorem(Base):
    __tablename__ = "theorem"
    __table_args__ = (
        CheckConstraint("status IN ('conjecture', 'proven')", name="known_status"),
        UniqueConstraint("namespace_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    namespace_id: Mapped[int] = mapped_column(ForeignKey("namespace.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    conclusion_formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="conjecture")
    description: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    conclusion_formula: Mapped[Formula] = relationship(lazy="joined")
    namespace: Mapped[Namespace] = relationship(lazy="joined")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary="theorem_tag",
        lazy="selectin",
        viewonly=True,
        order_by=tag_name_order,
    )
    premises: Mapped[list[TheoremPremise]] = relationship(
        back_populates="theorem",
        cascade="all, delete-orphan",
        order_by="TheoremPremise.ord",
        lazy="raise",
    )


class TheoremPremise(Base):
    __tablename__ = "theorem_premise"
    __table_args__ = (
        CheckConstraint("ord >= 0", name="ord_nonnegative"),
    )

    theorem_id: Mapped[int] = mapped_column(
        ForeignKey("theorem.id", ondelete="CASCADE"), primary_key=True
    )
    ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)

    theorem: Mapped[Theorem] = relationship(back_populates="premises")
    formula: Mapped[Formula] = relationship(lazy="joined")


class Proof(Base):
    __tablename__ = "proof"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'verified', 'rejected')", name="known_status"),
        UniqueConstraint("theorem_id", "identity_ordinal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, default=new_public_id
    )
    theorem_id: Mapped[int] = mapped_column(ForeignKey("theorem.id"), nullable=False)
    identity_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    theorem: Mapped[Theorem] = relationship(lazy="joined")
    steps: Mapped[list[ProofStep]] = relationship(
        back_populates="proof",
        cascade="all, delete-orphan",
        foreign_keys="ProofStep.proof_id",
        order_by="ProofStep.ord",
        lazy="raise",
    )


class ProofIdentitySequence(Base):
    """Monotone proof identity allocation that survives proof deletion."""

    __tablename__ = "proof_identity_sequence"

    theorem_id: Mapped[int] = mapped_column(
        ForeignKey("theorem.id", ondelete="CASCADE"), primary_key=True
    )
    next_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class ProofStep(Base):
    __tablename__ = "proof_step"
    __table_args__ = (
        CheckConstraint("ord >= 0", name="ord_nonnegative"),
        CheckConstraint(
            "step_kind IN ('premise', 'assumption', 'axiom', 'theorem', 'rule')",
            name="known_step_kind",
        ),
        CheckConstraint(
            "(step_kind = 'premise' AND premise_ord IS NOT NULL "
            "AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) "
            "OR (step_kind = 'assumption' AND premise_ord IS NULL "
            "AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) "
            "OR (step_kind = 'axiom' AND axiom_id IS NOT NULL "
            "AND premise_ord IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) "
            "OR (step_kind = 'theorem' AND applied_proof_id IS NOT NULL "
            "AND premise_ord IS NULL AND axiom_id IS NULL AND inference_rule_id IS NULL) "
            "OR (step_kind = 'rule' AND inference_rule_id IS NOT NULL "
            "AND premise_ord IS NULL AND axiom_id IS NULL AND applied_proof_id IS NULL)",
            name="kind_column_consistency",
        ),
        CheckConstraint("step_kind = 'rule' OR gen_variable_symbol_id IS NULL", name="gen_variable_only_for_rule"),
    )

    proof_id: Mapped[int] = mapped_column(
        ForeignKey("proof.id", ondelete="CASCADE"), primary_key=True
    )
    ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_kind: Mapped[str] = mapped_column(Text, nullable=False)
    conclusion_formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)
    premise_ord: Mapped[int | None] = mapped_column(Integer)
    axiom_id: Mapped[int | None] = mapped_column(ForeignKey("axiom.id"))
    applied_proof_id: Mapped[int | None] = mapped_column(ForeignKey("proof.id"))
    inference_rule_id: Mapped[int | None] = mapped_column(ForeignKey("inference_rule.id"))
    gen_variable_symbol_id: Mapped[int | None] = mapped_column(ForeignKey("symbol.id"))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    proof: Mapped[Proof] = relationship(back_populates="steps", foreign_keys=[proof_id])
    conclusion_formula: Mapped[Formula] = relationship(lazy="joined")
    axiom: Mapped[Axiom | None] = relationship(lazy="joined")
    applied_proof: Mapped[Proof | None] = relationship(foreign_keys=[applied_proof_id], lazy="joined")
    inference_rule: Mapped[InferenceRule | None] = relationship(lazy="joined")


class ProofStepArg(Base):
    __tablename__ = "proof_step_arg"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proof_id", "step_ord"],
            ["proof_step.proof_id", "proof_step.ord"],
            ondelete="CASCADE",
            name="fk_proof_step_arg_step",
        ),
        ForeignKeyConstraint(
            ["proof_id", "referenced_step_ord"],
            ["proof_step.proof_id", "proof_step.ord"],
            name="fk_proof_step_arg_referenced_step",
            ondelete="CASCADE",
        ),
        CheckConstraint("arg_ord >= 0", name="arg_ord_nonnegative"),
        CheckConstraint("referenced_step_ord < step_ord", name="references_prior_step"),
    )

    proof_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    arg_ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    referenced_step_ord: Mapped[int] = mapped_column(Integer, nullable=False)


class ProofStepSubstTerm(Base):
    __tablename__ = "proof_step_subst_term"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proof_id", "step_ord"],
            ["proof_step.proof_id", "proof_step.ord"],
            ondelete="CASCADE",
        ),
    )

    proof_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"), primary_key=True)
    target_formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)


class ProofStepSubstProp(Base):
    __tablename__ = "proof_step_subst_prop"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proof_id", "step_ord"],
            ["proof_step.proof_id", "proof_step.ord"],
            ondelete="CASCADE",
        ),
    )

    proof_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"), primary_key=True)
    body_formula_id: Mapped[int] = mapped_column(ForeignKey("formula.id"), nullable=False)


class ProofStepSubstPropParam(Base):
    __tablename__ = "proof_step_subst_prop_param"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proof_id", "step_ord", "source_symbol_id"],
            [
                "proof_step_subst_prop.proof_id",
                "proof_step_subst_prop.step_ord",
                "proof_step_subst_prop.source_symbol_id",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint("ord >= 0", name="ord_nonnegative"),
    )

    proof_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_symbol_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ord: Mapped[int] = mapped_column(Integer, primary_key=True)
    formal_param_symbol_id: Mapped[int] = mapped_column(ForeignKey("symbol.id"), nullable=False)
