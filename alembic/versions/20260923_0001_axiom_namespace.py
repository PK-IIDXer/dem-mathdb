"""Give axioms a namespace like symbols and theorems.

Existing axioms were created in ``dem.foundation.logic`` (their public IDs
were computed from that namespace), so they are placed there.  Public IDs are
left unchanged: a public ID is fixed when a row is created, and a later move
to another namespace keeps it (lean-import-design §5.2).

Revision ID: 20260923_0001
Revises: 20260918_0005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from dem.db.triggers import TriggerSpec, create_tier_a_triggers


revision = "20260923_0001"
down_revision = "20260918_0005"
branch_labels = None
depends_on = None

DEFAULT_NAMESPACE = "dem.foundation.logic"
# SQLite rebuilds the table for NOT NULL and the foreign key, which drops its
# triggers; the axiom guard is installed again afterwards.
_AXIOM_TRIGGERS = (TriggerSpec("axiom_formula_immutable_update", "axiom", "UPDATE"),)


def _namespace_id(connection, name: str) -> int:
    existing = connection.scalar(
        sa.text("SELECT id FROM namespace WHERE name = :name"), {"name": name}
    )
    if existing is not None:
        return int(existing)
    parent_name = name.rpartition(".")[0]
    parent_id = _namespace_id(connection, parent_name) if "." in parent_name else None
    connection.execute(
        sa.text("INSERT INTO namespace (name, parent_id) VALUES (:name, :parent_id)"),
        {"name": name, "parent_id": parent_id},
    )
    return int(
        connection.scalar(
            sa.text("SELECT id FROM namespace WHERE name = :name"), {"name": name}
        )
    )


def upgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("axiom") as batch:
        batch.add_column(sa.Column("namespace_id", sa.Integer(), nullable=True))
    if connection.scalar(sa.text("SELECT COUNT(*) FROM axiom")):
        connection.execute(
            sa.text("UPDATE axiom SET namespace_id = :namespace_id"),
            {"namespace_id": _namespace_id(connection, DEFAULT_NAMESPACE)},
        )
    with op.batch_alter_table("axiom") as batch:
        batch.alter_column("namespace_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_axiom_namespace_id_namespace", "namespace", ["namespace_id"], ["id"]
        )
    create_tier_a_triggers(connection, _AXIOM_TRIGGERS)


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("axiom") as batch:
        batch.drop_constraint("fk_axiom_namespace_id_namespace", type_="foreignkey")
        batch.drop_column("namespace_id")
    create_tier_a_triggers(connection, _AXIOM_TRIGGERS)
