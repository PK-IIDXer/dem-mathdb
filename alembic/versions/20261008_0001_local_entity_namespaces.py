"""Scope user-authored entity names to namespaces.

Revision ID: 20261008_0001
Revises: 20260923_0003
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from dem.db.triggers import TriggerSpec, create_tier_a_triggers


revision = "20261008_0001"
down_revision = "20260923_0003"
branch_labels = None
depends_on = None

DEFAULT_NAMESPACE = "dem.foundation.logic"
_AXIOM_TRIGGERS = (
    TriggerSpec("axiom_formula_immutable_update", "axiom", "UPDATE"),
)


def _namespace_id(connection, name: str) -> int:
    existing = connection.scalar(
        sa.text("SELECT id FROM namespace WHERE name = :name"), {"name": name}
    )
    if existing is None:
        raise RuntimeError(f"required namespace {name!r} does not exist")
    return int(existing)


def upgrade() -> None:
    connection = op.get_bind()

    op.create_index(
        "ix_symbol_identity",
        "symbol",
        ["id", "namespace_id", "name"],
        unique=True,
    )

    with op.batch_alter_table("definition") as batch:
        batch.add_column(sa.Column("namespace_id", sa.Integer(), nullable=True))
    connection.execute(
        sa.text(
            "UPDATE definition SET namespace_id = ("
            "SELECT symbol.namespace_id FROM symbol "
            "WHERE symbol.id = definition.new_symbol_id)"
        )
    )
    with op.batch_alter_table("definition") as batch:
        batch.drop_constraint("uq_definition_name", type_="unique")
        batch.alter_column("namespace_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_definition_namespace_id_namespace",
            "namespace",
            ["namespace_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_definition_symbol_identity",
            "symbol",
            ["new_symbol_id", "namespace_id", "name"],
            ["id", "namespace_id", "name"],
        )
        batch.create_unique_constraint(
            "uq_definition_namespace_id", ["namespace_id", "name"]
        )

    with op.batch_alter_table("axiom") as batch:
        batch.drop_constraint("uq_axiom_name", type_="unique")
        batch.create_unique_constraint(
            "uq_axiom_namespace_id", ["namespace_id", "name"]
        )
    create_tier_a_triggers(connection, _AXIOM_TRIGGERS)

    with op.batch_alter_table("axiom_system") as batch:
        batch.add_column(sa.Column("namespace_id", sa.Integer(), nullable=True))
    connection.execute(
        sa.text("UPDATE axiom_system SET namespace_id = :namespace_id"),
        {"namespace_id": _namespace_id(connection, DEFAULT_NAMESPACE)},
    )
    with op.batch_alter_table("axiom_system") as batch:
        batch.drop_constraint("uq_axiom_system_name", type_="unique")
        batch.alter_column("namespace_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key(
            "fk_axiom_system_namespace_id_namespace",
            "namespace",
            ["namespace_id"],
            ["id"],
        )
        batch.create_unique_constraint(
            "uq_axiom_system_namespace_id", ["namespace_id", "name"]
        )


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("axiom_system") as batch:
        batch.drop_constraint("uq_axiom_system_namespace_id", type_="unique")
        batch.drop_constraint(
            "fk_axiom_system_namespace_id_namespace", type_="foreignkey"
        )
        batch.create_unique_constraint("uq_axiom_system_name", ["name"])
        batch.drop_column("namespace_id")

    with op.batch_alter_table("axiom") as batch:
        batch.drop_constraint("uq_axiom_namespace_id", type_="unique")
        batch.create_unique_constraint("uq_axiom_name", ["name"])
    create_tier_a_triggers(connection, _AXIOM_TRIGGERS)

    with op.batch_alter_table("definition") as batch:
        batch.drop_constraint("uq_definition_namespace_id", type_="unique")
        batch.drop_constraint("fk_definition_symbol_identity", type_="foreignkey")
        batch.drop_constraint(
            "fk_definition_namespace_id_namespace", type_="foreignkey"
        )
        batch.create_unique_constraint("uq_definition_name", ["name"])
        batch.drop_column("namespace_id")

    op.drop_index("ix_symbol_identity", table_name="symbol")
