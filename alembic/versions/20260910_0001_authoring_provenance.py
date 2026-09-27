"""Add authoring provenance audit metadata.

Revision ID: 20260910_0001
Revises: 20260908_0001
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260910_0001"
down_revision = "20260908_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authoring_provenance",
        sa.Column("entity_kind", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("via", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("user_input", sa.Text(), nullable=True),
        sa.Column("accepted_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
        sa.PrimaryKeyConstraint("entity_kind", "entity_id", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("authoring_provenance")
