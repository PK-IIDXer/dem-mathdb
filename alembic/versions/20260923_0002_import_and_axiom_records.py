"""Add the axiom-introduction record and the import record (N11-C).

Both tables are records beside the proof data and are never read by proof
validation, the axiom-dependency computation or ``theorem.status``
(lean-import-design §2.8, §3.4).  Nothing is written to them by this
revision.

Revision ID: 20260923_0002
Revises: 20260923_0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260923_0002"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None

_CHECK_RESULTS = "('passed', 'failed', 'not_run')"


def upgrade() -> None:
    op.create_table(
        "axiom_record",
        sa.Column("axiom_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("theory", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("strength", sa.Text(), nullable=False),
        sa.Column("foundation_version", sa.Text(), nullable=False),
        sa.Column("introduced_by", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=False),
        sa.Column("introduced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["axiom_id"], ["axiom.id"], name="fk_axiom_record_axiom_id_axiom"
        ),
        sa.PrimaryKeyConstraint("axiom_id", name="pk_axiom_record"),
    )
    op.create_table(
        "import_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("theorem_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_system_version", sa.Text(), nullable=False),
        sa.Column("library", sa.Text(), nullable=False),
        sa.Column("library_version", sa.Text(), nullable=False),
        sa.Column("library_commit", sa.Text(), nullable=False),
        sa.Column("declaration", sa.Text(), nullable=False),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("file", sa.Text(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("source_statement", sa.Text(), nullable=False),
        sa.Column("source_statement_hash", sa.Text(), nullable=False),
        sa.Column("universe_params", sa.Integer(), nullable=False),
        sa.Column("source_axioms", sa.Text(), nullable=False),
        sa.Column("translator_version", sa.Text(), nullable=False),
        sa.Column("mapping_table_version", sa.Text(), nullable=False),
        sa.Column("prop_encoding", sa.Text(), nullable=False),
        sa.Column("check_model", sa.Text(), nullable=False),
        sa.Column("check_roundtrip", sa.Text(), nullable=False),
        sa.Column("check_toolchain", sa.Text(), nullable=True),
        sa.Column("check_artifact_hash", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("copyright", sa.Text(), nullable=True),
        sa.Column("authors", sa.Text(), nullable=True),
        sa.Column("upstream_origin", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"check_model IN {_CHECK_RESULTS}", name="ck_import_record_known_check_model"
        ),
        sa.CheckConstraint(
            f"check_roundtrip IN {_CHECK_RESULTS}",
            name="ck_import_record_known_check_roundtrip",
        ),
        sa.CheckConstraint(
            "upstream_origin IN ('human', 'ai', 'unknown')",
            name="ck_import_record_known_upstream_origin",
        ),
        sa.CheckConstraint("line > 0", name="ck_import_record_line_positive"),
        sa.CheckConstraint(
            "universe_params >= 0", name="ck_import_record_universe_params_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["theorem_id"],
            ["theorem.id"],
            name="fk_import_record_theorem_id_theorem",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_record"),
        sa.UniqueConstraint(
            "theorem_id",
            "source_system",
            "library",
            "library_commit",
            "declaration",
            name="uq_import_record_theorem_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("import_record")
    op.drop_table("axiom_record")
