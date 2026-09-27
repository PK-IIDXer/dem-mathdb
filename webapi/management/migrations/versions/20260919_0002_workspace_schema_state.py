"""Track workspace schema health.

Revision ID: 20260919_mgmt_0002
Revises: 20260911_mgmt_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20260919_mgmt_0002"
down_revision = "20260911_mgmt_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace", sa.Column("template_fingerprint", sa.Text(), nullable=True)
    )
    op.add_column("workspace", sa.Column("schema_revision", sa.Text(), nullable=True))
    op.add_column(
        "workspace",
        sa.Column(
            "schema_state",
            sa.Text(),
            nullable=False,
            server_default="upgrading",
        ),
    )
    op.add_column("workspace", sa.Column("schema_error", sa.Text(), nullable=True))
    op.add_column(
        "workspace",
        sa.Column("schema_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("workspace") as batch:
        batch.create_check_constraint(
            "known_schema_state",
            "schema_state IN ('ready', 'upgrading', 'upgrade_blocked')",
        )


def downgrade() -> None:
    with op.batch_alter_table("workspace") as batch:
        batch.drop_constraint("known_schema_state", type_="check")
        batch.drop_column("schema_checked_at")
        batch.drop_column("schema_error")
        batch.drop_column("schema_state")
        batch.drop_column("schema_revision")
        batch.drop_column("template_fingerprint")
