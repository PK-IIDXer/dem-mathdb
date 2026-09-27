"""Records that sit beside the proof data and never enter validation.

``AxiomRecord`` is WHITEPAPER §7.4 / lean-import-design §2.8: one row per
non-definitional axiom, written by the person who introduces the axiom.
``ImportRecord`` is lean-import-design §3.4: where an imported statement came
from.  A theorem with an import record stays a conjecture until DEM's own
kernel accepts a proof; nothing here is read by proof validation, by the
axiom-dependency computation or by ``theorem.status``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dem.db.base import Base


class AxiomRecord(Base):
    __tablename__ = "axiom_record"

    axiom_id: Mapped[int] = mapped_column(ForeignKey("axiom.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON array of the names of the axiom systems the axiom was introduced into.
    theory: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[str] = mapped_column(Text, nullable=False)
    foundation_version: Mapped[str] = mapped_column(Text, nullable=False)
    introduced_by: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(Text, nullable=False)
    introduced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


_CHECK_RESULTS = "('passed', 'failed', 'not_run')"


class ImportRecord(Base):
    __tablename__ = "import_record"
    __table_args__ = (
        CheckConstraint(f"check_model IN {_CHECK_RESULTS}", name="known_check_model"),
        CheckConstraint(f"check_roundtrip IN {_CHECK_RESULTS}", name="known_check_roundtrip"),
        CheckConstraint(
            "upstream_origin IN ('human', 'ai', 'unknown')", name="known_upstream_origin"
        ),
        CheckConstraint("line > 0", name="line_positive"),
        CheckConstraint("universe_params >= 0", name="universe_params_nonnegative"),
        UniqueConstraint(
            "theorem_id", "source_system", "library", "library_commit", "declaration"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    theorem_id: Mapped[int] = mapped_column(
        ForeignKey("theorem.id", ondelete="CASCADE"), nullable=False
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_system_version: Mapped[str] = mapped_column(Text, nullable=False)
    library: Mapped[str] = mapped_column(Text, nullable=False)
    library_version: Mapped[str] = mapped_column(Text, nullable=False)
    library_commit: Mapped[str] = mapped_column(Text, nullable=False)
    declaration: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    file: Mapped[str] = mapped_column(Text, nullable=False)
    line: Mapped[int] = mapped_column(Integer, nullable=False)
    source_statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_statement_hash: Mapped[str] = mapped_column(Text, nullable=False)
    universe_params: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON arrays: the source system's reported set of axioms on which the
    # statement depends, and P1 / P2 per Prop binder.
    source_axioms: Mapped[str] = mapped_column(Text, nullable=False)
    translator_version: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_table_version: Mapped[str] = mapped_column(Text, nullable=False)
    prop_encoding: Mapped[str] = mapped_column(Text, nullable=False)
    check_model: Mapped[str] = mapped_column(Text, nullable=False)
    check_roundtrip: Mapped[str] = mapped_column(Text, nullable=False)
    check_toolchain: Mapped[str | None] = mapped_column(Text)
    check_artifact_hash: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license: Mapped[str] = mapped_column(Text, nullable=False)
    copyright: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[str | None] = mapped_column(Text)
    upstream_origin: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
