"""Add surface-syntax aliases for symbols.

Revision ID: 20260907_0001
Revises: 20260906_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0001"
down_revision = "20260906_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbol_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint("source IN ('builtin', 'user')", name="known_source"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbol.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias"),
    )


def downgrade() -> None:
    op.drop_table("symbol_alias")
