"""Add permanent axiom-system IDs and immutable entity identities."""
from __future__ import annotations
from uuid import UUID, uuid5
from alembic import op
import sqlalchemy as sa
from dem.db.triggers import (
    PUBLIC_ID_IMMUTABILITY_TRIGGER_SPECS,
    create_tier_a_triggers,
    create_tier_b_immutability_triggers,
)
revision = "20261013_0001"
down_revision = "20261008_0001"
branch_labels = None
depends_on = None
PUBLIC_ID_NAMESPACE = UUID("a5643d59-43f3-5ce2-9c31-633b24415486")


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("axiom_system", sa.Column("public_id", sa.Text(), nullable=True))
    rows = [
        {
            "id": row.id,
            "public_id": str(uuid5(PUBLIC_ID_NAMESPACE, f"axiom_system::{row.namespace}::{row.name}")),
        }
        for row in connection.execute(sa.text(
            "SELECT system.id, namespace.name AS namespace, system.name "
            "FROM axiom_system AS system JOIN namespace ON namespace.id = system.namespace_id"
        ))
    ]
    if rows:
        connection.execute(sa.text("UPDATE axiom_system SET public_id = :public_id WHERE id = :id"), rows)
    with op.batch_alter_table("axiom_system") as batch:
        batch.alter_column("public_id", existing_type=sa.Text(), nullable=False)
        batch.create_unique_constraint("uq_axiom_system_public_id", ["public_id"])
    # SQLite batch recreation drops table triggers. Restore all applicable guards.
    create_tier_a_triggers(connection)
    create_tier_b_immutability_triggers(connection)


def downgrade() -> None:
    connection = op.get_bind()
    for spec in PUBLIC_ID_IMMUTABILITY_TRIGGER_SPECS:
        suffix = f" ON {spec.table}" if connection.dialect.name == "postgresql" else ""
        connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {spec.name}{suffix}")
    with op.batch_alter_table("axiom_system") as batch:
        batch.drop_constraint("uq_axiom_system_public_id", type_="unique")
        batch.drop_column("public_id")
    create_tier_a_triggers(connection)
