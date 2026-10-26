"""Add the display-only Lean/DEM axiom-dependency comparison to import records.

No data is backfilled: the comparison is written by the Lean import's rebuild
step once a DEM proof exists, from that foundation's own data.  The column is
added in place (no batch recreation), so no trigger is dropped.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
revision = "20261016_0002"
down_revision = "20261016_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("import_record", sa.Column("axiom_comparison", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_record") as batch:
        batch.drop_column("axiom_comparison")
