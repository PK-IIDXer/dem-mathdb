"""Add distribution releases and nullable entity ownership (no kernel changes)."""
from contextlib import contextmanager

from alembic import op
import sqlalchemy as sa
from dem.db.triggers import create_tier_a_triggers, create_tier_b_immutability_triggers

revision = "20261019_0001"
down_revision = "20261016_0002"
branch_labels = None
depends_on = None

ENTITIES = ("symbol", "definition", "axiom", "axiom_system", "theorem", "proof")


@contextmanager
def _batch_tables():
    connection = op.get_bind()
    sqlite = connection.dialect.name == "sqlite"
    previous = connection.exec_driver_sql("PRAGMA legacy_alter_table").scalar() if sqlite else None
    if sqlite:
        # Other tables' triggers reference the briefly absent batch table.
        # Keep them installed; only suppress SQLite's rename-time SQL rewrite.
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
    try:
        yield
    finally:
        if sqlite:
            connection.exec_driver_sql(f"PRAGMA legacy_alter_table={int(previous)}")


def upgrade():
    op.create_table('package',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('owner', sa.Text(), nullable=False),
    sa.Column('visibility', sa.Text(), server_default='private', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("visibility IN ('public', 'private')", name=op.f('ck_package_known_visibility')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_package')),
    sa.UniqueConstraint('name', name=op.f('uq_package_name'))
    )
    op.create_table('package_release',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('dem_runtime_range', sa.Text(), nullable=False),
    sa.Column('manifest', sa.JSON(), nullable=False),
    sa.Column('content_digest', sa.Text(), nullable=True),
    sa.Column('yanked', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['package_id'], ['package.id'], name=op.f('fk_package_release_package_id_package')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_package_release')),
    sa.UniqueConstraint('package_id', 'version', name=op.f('uq_package_release_package_id'))
    )
    op.create_table('release_dependency',
    sa.Column('release_id', sa.Integer(), nullable=False),
    sa.Column('depends_package_id', sa.Integer(), nullable=False),
    sa.Column('range', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['depends_package_id'], ['package.id'], name=op.f('fk_release_dependency_depends_package_id_package')),
    sa.ForeignKeyConstraint(['release_id'], ['package_release.id'], name=op.f('fk_release_dependency_release_id_package_release')),
    sa.PrimaryKeyConstraint('release_id', 'depends_package_id', name=op.f('pk_release_dependency'))
    )
    op.create_table('release_lock_entry',
    sa.Column('release_id', sa.Integer(), nullable=False),
    sa.Column('locked_release_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('release_id <> locked_release_id', name=op.f('ck_release_lock_entry_not_self')),
    sa.ForeignKeyConstraint(['locked_release_id'], ['package_release.id'], name=op.f('fk_release_lock_entry_locked_release_id_package_release')),
    sa.ForeignKeyConstraint(['release_id'], ['package_release.id'], name=op.f('fk_release_lock_entry_release_id_package_release')),
    sa.PrimaryKeyConstraint('release_id', 'locked_release_id', name=op.f('pk_release_lock_entry'))
    )
    op.create_table('installed_release',
    sa.Column('release_id', sa.Integer(), nullable=False),
    sa.Column('installed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['release_id'], ['package_release.id'], name=op.f('fk_installed_release_release_id_package_release')),
    sa.PrimaryKeyConstraint('release_id', name=op.f('pk_installed_release'))
    )
    with _batch_tables():
        for table in ENTITIES:
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("release_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(f"fk_{table}_release_id_package_release", "package_release", ["release_id"], ["id"])
    create_tier_a_triggers(op.get_bind())
    create_tier_b_immutability_triggers(op.get_bind())


def downgrade():
    with _batch_tables():
        for table in reversed(ENTITIES):
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(f"fk_{table}_release_id_package_release", type_="foreignkey")
                batch.drop_column("release_id")
    for table in ("installed_release", "release_lock_entry", "release_dependency", "package_release", "package"):
        op.drop_table(table)
    create_tier_a_triggers(op.get_bind())
    create_tier_b_immutability_triggers(op.get_bind())
