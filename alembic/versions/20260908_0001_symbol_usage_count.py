"""Persist distinct-formula usage counts on symbols.

Revision ID: 20260908_0001
Revises: 20260907_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0001"
down_revision = "20260907_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "symbol",
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(
        """
        UPDATE symbol
        SET usage_count = (
            SELECT COUNT(DISTINCT formula_token.formula_id)
            FROM formula_token
            WHERE formula_token.symbol_id = symbol.id
        )
        """
    )


def downgrade() -> None:
    op.drop_column("symbol", "usage_count")
