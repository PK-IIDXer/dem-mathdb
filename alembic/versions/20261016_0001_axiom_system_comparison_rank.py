"""Add the seed-owned display rank for default axiom-system comparisons.

No data is backfilled: which systems a foundation compares against belongs to
that foundation's seed data, which sets the rank idempotently on its next run.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from dem.db.triggers import create_tier_a_triggers, create_tier_b_immutability_triggers
revision = "20261016_0001"
down_revision = "20261013_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("axiom_system", sa.Column("comparison_rank", sa.Integer(), nullable=True))
    with op.batch_alter_table("axiom_system") as batch:
        batch.create_unique_constraint("uq_axiom_system_comparison_rank", ["comparison_rank"])
    # SQLite batch recreation drops table triggers. Restore all applicable guards.
    create_tier_a_triggers(connection)
    create_tier_b_immutability_triggers(connection)


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("axiom_system") as batch:
        batch.drop_constraint("uq_axiom_system_comparison_rank", type_="unique")
        batch.drop_column("comparison_rank")
    create_tier_a_triggers(connection)
    create_tier_b_immutability_triggers(connection)
