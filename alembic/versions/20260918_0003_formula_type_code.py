"""Add stable machine-readable formula type codes.

Revision ID: 20260918_0003
Revises: 20260918_0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260918_0003"
down_revision = "20260918_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("formula_type") as batch:
        batch.add_column(sa.Column("code", sa.Text(), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE formula_type SET code = 'term' WHERE name = :name"),
        {"name": "項"},
    )
    connection.execute(
        sa.text(
            "UPDATE formula_type SET code = 'proposition' WHERE name = :name"
        ),
        {"name": "命題"},
    )
    unknown = connection.scalar(
        sa.text("SELECT COUNT(*) FROM formula_type WHERE code IS NULL")
    )
    if unknown:
        raise RuntimeError(
            "formula_type contains rows without a stable term/proposition mapping"
        )

    with op.batch_alter_table("formula_type") as batch:
        batch.alter_column("code", existing_type=sa.Text(), nullable=False)
        batch.create_unique_constraint("uq_formula_type_code", ["code"])
        batch.create_check_constraint(
            "ck_formula_type_known_code",
            "code IN ('term', 'proposition')",
        )


def downgrade() -> None:
    with op.batch_alter_table("formula_type") as batch:
        batch.drop_constraint("ck_formula_type_known_code", type_="check")
        batch.drop_constraint("uq_formula_type_code", type_="unique")
        batch.drop_column("code")
