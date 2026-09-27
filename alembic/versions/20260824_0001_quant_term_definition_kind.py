"""allow definition.kind = 'quant_term'

`quant_term` (term-quantifier definition, `(N x. phi(x)) = B`) has been one of
the documented definition kinds since the first design revision, but it never
made it into the implementation: the initial schema's `known_kind` CHECK lists
`function_desc` where the design doc lists `quant_term`. This widens the CHECK
so `DefinitionService` can register the kind it was always meant to support.

No data migration: no row can currently carry the new value.

Production SQLite databases are normally created from the models by
`DemApi.create_schema()`, but the migration history must also remain runnable
against an empty SQLite database for development and verification.

Revision ID: 20260824_0001
Revises: 20260812_0001
Create Date: 2026-08-24
"""

from __future__ import annotations

from alembic import op


revision = '20260824_0001'
down_revision = '20260812_0001'
branch_labels = None
depends_on = None

_OLD = "kind IN ('predicate', 'function', 'logical', 'quant_prop', 'function_desc')"
_NEW = (
    "kind IN ('predicate', 'function', 'logical', 'quant_prop', 'quant_term', "
    "'function_desc')"
)


def _replace_check(condition: str) -> None:
    # op.f() keeps the metadata naming convention ("ck_%(table_name)s_%(constraint_name)s")
    # from prefixing the already-final name a second time.
    name = op.f('ck_definition_known_kind')
    # SQLite cannot ALTER CHECK constraints directly.  Batch mode rebuilds the
    # table there and remains a normal ALTER on databases that support it.
    with op.batch_alter_table('definition') as batch:
        batch.drop_constraint(name, type_='check')
        batch.create_check_constraint(name, condition)


def upgrade() -> None:
    _replace_check(_NEW)


def downgrade() -> None:
    _replace_check(_OLD)
