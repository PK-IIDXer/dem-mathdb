"""Make accepted formulas and symbol semantics immutable.

Revision ID: 20260918_0005
Revises: 20260918_0004
"""

from __future__ import annotations

from alembic import op

from dem.db.triggers import (
    create_tier_b_immutability_triggers,
    drop_tier_b_immutability_triggers,
)


revision = "20260918_0005"
down_revision = "20260918_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tier_b_immutability_triggers(op.get_bind())


def downgrade() -> None:
    drop_tier_b_immutability_triggers(op.get_bind())
