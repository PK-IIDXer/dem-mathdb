"""Add the Tier B formula well-formedness gate.

Revision ID: 20260918_0004
Revises: 20260918_0003
"""

from __future__ import annotations

from alembic import op

from dem.db.triggers import (
    create_tier_b_wellformed_gate,
    drop_tier_b_wellformed_gate,
)


revision = "20260918_0004"
down_revision = "20260918_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tier_b_wellformed_gate(op.get_bind())


def downgrade() -> None:
    drop_tier_b_wellformed_gate(op.get_bind())
