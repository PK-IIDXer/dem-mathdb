"""Complete Tier A proof and axiom identity guards.

Revision ID: 20260918_0002
Revises: 20260918_0001
"""

from __future__ import annotations

from alembic import op

from dem.db.triggers import (
    TIER_A_EXTENSION_TRIGGER_SPECS,
    create_tier_a_triggers,
    drop_tier_a_trigger_specs,
)


revision = "20260918_0002"
down_revision = "20260918_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_tier_a_triggers(op.get_bind(), TIER_A_EXTENSION_TRIGGER_SPECS)


def downgrade() -> None:
    drop_tier_a_trigger_specs(op.get_bind(), TIER_A_EXTENSION_TRIGGER_SPECS)
