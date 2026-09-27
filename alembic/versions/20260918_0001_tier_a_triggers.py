"""Add Tier A proof immutability and state-transition triggers.

Revision ID: 20260918_0001
Revises: 20260910_0002
"""

from __future__ import annotations

from alembic import op

from dem.db.triggers import (
    FOUNDATIONAL_TIER_A_TRIGGER_SPECS,
    create_tier_a_triggers,
    drop_tier_a_triggers,
)


revision = "20260918_0001"
down_revision = "20260910_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both proof_step_arg foreign keys must cascade for a draft proof to be
    # deletable on PostgreSQL regardless of the order chosen for FK actions.
    with op.batch_alter_table("proof_step_arg") as batch:
        batch.drop_constraint(
            "fk_proof_step_arg_referenced_step", type_="foreignkey"
        )
        batch.create_foreign_key(
            "fk_proof_step_arg_referenced_step",
            "proof_step",
            ["proof_id", "referenced_step_ord"],
            ["proof_id", "ord"],
            ondelete="CASCADE",
        )
    create_tier_a_triggers(op.get_bind(), FOUNDATIONAL_TIER_A_TRIGGER_SPECS)


def downgrade() -> None:
    drop_tier_a_triggers(op.get_bind())
    with op.batch_alter_table("proof_step_arg") as batch:
        batch.drop_constraint(
            "fk_proof_step_arg_referenced_step", type_="foreignkey"
        )
        batch.create_foreign_key(
            "fk_proof_step_arg_referenced_step",
            "proof_step",
            ["proof_id", "referenced_step_ord"],
            ["proof_id", "ord"],
        )
