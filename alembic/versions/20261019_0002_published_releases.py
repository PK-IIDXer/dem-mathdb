"""Protect published releases and their content in both database dialects."""
from alembic import op
from dem.db.package_triggers import create_published_triggers, drop_published_triggers

revision = "20261019_0002"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None


def upgrade():
    create_published_triggers(op.get_bind())


def downgrade():
    drop_published_triggers(op.get_bind())
