"""Index formula-token symbol lookup for authoring search.

Revision ID: 20260906_0001
Revises: 20260824_0001
"""
from alembic import op

revision = "20260906_0001"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_formula_token_symbol_formula", "formula_token", ["symbol_id", "formula_id"])


def downgrade() -> None:
    op.drop_index("ix_formula_token_symbol_formula", table_name="formula_token")
