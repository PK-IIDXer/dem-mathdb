"""A theorem is proven only through a verified proof; proofs start as drafts.

lean-import-design §3.7 (decision D7).  Existing rows are checked first: the
revision refuses to install the guards over a theorem that is already proven
without a verified proof.

Revision ID: 20260923_0003
Revises: 20260923_0002
"""

from __future__ import annotations

from alembic import op

from dem.db.triggers import (
    PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS,
    create_proven_requires_verified_triggers,
    drop_tier_a_trigger_specs,
)


revision = "20260923_0003"
down_revision = "20260923_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_proven_requires_verified_triggers(op.get_bind())


def downgrade() -> None:
    drop_tier_a_trigger_specs(op.get_bind(), PROVEN_REQUIRES_VERIFIED_TRIGGER_SPECS)
