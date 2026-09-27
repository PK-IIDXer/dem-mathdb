"""Add public identity, namespaces, and portable formula hashes.

Revision ID: 20260910_0002
Revises: 20260910_0001
"""
from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa


revision = "20260910_0002"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None

DEFAULT_NAMESPACE = "dem.foundation.logic"
PUBLIC_ID_NAMESPACE = UUID("a5643d59-43f3-5ce2-9c31-633b24415486")


def _public_id(entity_kind: str, key: str) -> str:
    # Kept local so historical migrations do not depend on mutable app code.
    # tests/test_phase3_identity_migration.py pins this to dem.identity.
    return str(uuid5(PUBLIC_ID_NAMESPACE, f"{entity_kind}::{key}"))


def _execute_many(connection, sql: str, rows: list[dict]) -> None:
    # Named binds via sa.text work on every dialect; driver-level SQL would need
    # the driver's own paramstyle (qmark on SQLite, pyformat on psycopg).
    # An empty list would execute once without parameters, so skip it.
    if rows:
        connection.execute(sa.text(sql), rows)


def _hashes(connection, *, public: bool) -> dict[int, str]:
    symbol_key = dict(
        connection.execute(
            sa.text(
                "SELECT id, public_id FROM symbol" if public else "SELECT id, id FROM symbol"
            )
        ).all()
    )
    parts: dict[int, list[str]] = {}
    for formula_id, symbol_id, bound in connection.execute(
        sa.text(
            "SELECT formula_id, symbol_id, de_bruijn_index "
            "FROM formula_token ORDER BY formula_id, position"
        )
    ):
        part = f"S{symbol_key[symbol_id]};" if symbol_id is not None else f"B{bound};"
        parts.setdefault(formula_id, []).append(part)
    return {
        formula_id: hashlib.sha256("".join(value).encode()).hexdigest()
        for formula_id, value in parts.items()
    }


def _replace_hashes(connection, hashes: dict[int, str]) -> None:
    _execute_many(
        connection,
        "UPDATE formula SET hash = :hash WHERE id = :id",
        [
            {"hash": f"phase3-temporary-{formula_id}", "id": formula_id}
            for formula_id in hashes
        ],
    )
    _execute_many(
        connection,
        "UPDATE formula SET hash = :hash WHERE id = :id",
        [{"hash": value, "id": formula_id} for formula_id, value in hashes.items()],
    )


def upgrade() -> None:
    connection = op.get_bind()
    op.create_table(
        "namespace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["namespace.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    connection.execute(
        sa.text(
            "INSERT INTO namespace (id, name, parent_id) VALUES (1, 'dem.foundation', NULL)"
        )
    )
    connection.execute(
        sa.text("INSERT INTO namespace (id, name, parent_id) VALUES (2, :name, 1)"),
        {"name": DEFAULT_NAMESPACE},
    )
    if connection.dialect.name == "postgresql":
        # Explicit ids do not advance the SERIAL sequence; without this the next
        # namespace inserted without an id (dem.identity.ensure_namespace) reuses id 1.
        connection.execute(
            sa.text(
                "SELECT setval(pg_get_serial_sequence('namespace', 'id'), "
                "(SELECT MAX(id) FROM namespace))"
            )
        )

    for table in ("symbol", "formula", "axiom", "definition", "theorem", "proof"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("public_id", sa.Text(), nullable=True))
    with op.batch_alter_table("theorem") as batch:
        batch.add_column(sa.Column("namespace_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("proof") as batch:
        batch.add_column(sa.Column("identity_ordinal", sa.Integer(), nullable=True))

    connection.execute(sa.text("UPDATE symbol SET namespace_id = 2"))
    connection.execute(sa.text("UPDATE theorem SET namespace_id = 2"))

    _execute_many(
        connection,
        "UPDATE symbol SET public_id = :public_id WHERE id = :id",
        [
            {"public_id": _public_id("symbol", f"{namespace}::{name}"), "id": entity_id}
            for entity_id, name, namespace in connection.execute(
                sa.text(
                    "SELECT symbol.id, symbol.name, namespace.name FROM symbol "
                    "JOIN namespace ON namespace.id = symbol.namespace_id ORDER BY symbol.id"
                )
            ).all()
        ],
    )

    _execute_many(
        connection,
        "UPDATE theorem SET public_id = :public_id WHERE id = :id",
        [
            {"public_id": _public_id("theorem", f"{namespace}::{name}"), "id": entity_id}
            for entity_id, name, namespace in connection.execute(
                sa.text(
                    "SELECT theorem.id, theorem.name, namespace.name FROM theorem "
                    "JOIN namespace ON namespace.id = theorem.namespace_id ORDER BY theorem.id"
                )
            ).all()
        ],
    )

    _execute_many(
        connection,
        "UPDATE axiom SET public_id = :public_id WHERE id = :id",
        [
            {
                "public_id": _public_id("axiom", f"{DEFAULT_NAMESPACE}::{name}"),
                "id": entity_id,
            }
            for entity_id, name in connection.execute(
                sa.text("SELECT id, name FROM axiom ORDER BY id")
            ).all()
        ],
    )

    _execute_many(
        connection,
        "UPDATE definition SET public_id = :public_id WHERE id = :id",
        [
            {
                "public_id": _public_id("definition", f"{namespace}::{name}"),
                "id": entity_id,
            }
            for entity_id, name, namespace in connection.execute(
                sa.text(
                    "SELECT definition.id, definition.name, namespace.name FROM definition "
                    "JOIN symbol ON symbol.id = definition.new_symbol_id "
                    "JOIN namespace ON namespace.id = symbol.namespace_id ORDER BY definition.id"
                )
            ).all()
        ],
    )

    new_hashes = _hashes(connection, public=True)
    _replace_hashes(connection, new_hashes)
    _execute_many(
        connection,
        "UPDATE formula SET public_id = :public_id WHERE id = :id",
        [
            {"public_id": _public_id("formula", formula_hash), "id": formula_id}
            for formula_id, formula_hash in new_hashes.items()
        ],
    )

    next_ordinal: dict[int, int] = {}
    theorem_public_ids = dict(
        connection.execute(sa.text("SELECT id, public_id FROM theorem")).all()
    )
    proof_rows: list[dict] = []
    for proof_id, theorem_id in connection.execute(
        sa.text("SELECT id, theorem_id FROM proof ORDER BY theorem_id, id")
    ).all():
        ordinal = next_ordinal.get(theorem_id, 0)
        proof_rows.append(
            {
                "public_id": _public_id(
                    "proof", f"{theorem_public_ids[theorem_id]}::{ordinal}"
                ),
                "identity_ordinal": ordinal,
                "id": proof_id,
            }
        )
        next_ordinal[theorem_id] = ordinal + 1
    _execute_many(
        connection,
        "UPDATE proof SET public_id = :public_id, identity_ordinal = :identity_ordinal "
        "WHERE id = :id",
        proof_rows,
    )

    op.create_table(
        "proof_identity_sequence",
        sa.Column("theorem_id", sa.Integer(), nullable=False),
        sa.Column("next_ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["theorem_id"], ["theorem.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("theorem_id"),
    )
    _execute_many(
        connection,
        "INSERT INTO proof_identity_sequence (theorem_id, next_ordinal) "
        "VALUES (:theorem_id, :next_ordinal)",
        [
            {"theorem_id": theorem_id, "next_ordinal": ordinal}
            for theorem_id, ordinal in next_ordinal.items()
        ],
    )

    inspector = sa.inspect(connection)
    symbol_uniques = {item["name"] for item in inspector.get_unique_constraints("symbol")}
    theorem_uniques = {item["name"] for item in inspector.get_unique_constraints("theorem")}
    with op.batch_alter_table("symbol") as batch:
        if "uq_symbol_name" in symbol_uniques:
            batch.drop_constraint("uq_symbol_name", type_="unique")
        batch.alter_column("public_id", nullable=False)
        batch.alter_column("namespace_id", nullable=False)
        batch.create_unique_constraint("uq_symbol_public_id", ["public_id"])
        batch.create_unique_constraint("uq_symbol_namespace_id", ["namespace_id", "name"])
        batch.create_foreign_key(
            "fk_symbol_namespace_id_namespace", "namespace", ["namespace_id"], ["id"]
        )
    with op.batch_alter_table("theorem") as batch:
        if "uq_theorem_name" in theorem_uniques:
            batch.drop_constraint("uq_theorem_name", type_="unique")
        batch.alter_column("public_id", nullable=False)
        batch.alter_column("namespace_id", nullable=False)
        batch.create_unique_constraint("uq_theorem_public_id", ["public_id"])
        batch.create_unique_constraint("uq_theorem_namespace_id", ["namespace_id", "name"])
        batch.create_foreign_key(
            "fk_theorem_namespace_id_namespace", "namespace", ["namespace_id"], ["id"]
        )
    for table in ("formula", "axiom", "definition"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("public_id", nullable=False)
            batch.create_unique_constraint(f"uq_{table}_public_id", ["public_id"])
    with op.batch_alter_table("proof") as batch:
        batch.alter_column("public_id", nullable=False)
        batch.alter_column("identity_ordinal", nullable=False)
        batch.create_unique_constraint("uq_proof_public_id", ["public_id"])
        batch.create_unique_constraint(
            "uq_proof_theorem_identity_ordinal", ["theorem_id", "identity_ordinal"]
        )


def downgrade() -> None:
    connection = op.get_bind()
    _replace_hashes(connection, _hashes(connection, public=False))
    op.drop_table("proof_identity_sequence")
    with op.batch_alter_table("proof") as batch:
        batch.drop_constraint("uq_proof_theorem_identity_ordinal", type_="unique")
        batch.drop_constraint("uq_proof_public_id", type_="unique")
        batch.drop_column("identity_ordinal")
        batch.drop_column("public_id")
    for table in ("formula", "axiom", "definition"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"uq_{table}_public_id", type_="unique")
            batch.drop_column("public_id")
    with op.batch_alter_table("theorem") as batch:
        batch.drop_constraint("fk_theorem_namespace_id_namespace", type_="foreignkey")
        batch.drop_constraint("uq_theorem_namespace_id", type_="unique")
        batch.drop_constraint("uq_theorem_public_id", type_="unique")
        batch.create_unique_constraint("uq_theorem_name", ["name"])
        batch.drop_column("namespace_id")
        batch.drop_column("public_id")
    with op.batch_alter_table("symbol") as batch:
        batch.drop_constraint("fk_symbol_namespace_id_namespace", type_="foreignkey")
        batch.drop_constraint("uq_symbol_namespace_id", type_="unique")
        batch.drop_constraint("uq_symbol_public_id", type_="unique")
        batch.create_unique_constraint("uq_symbol_name", ["name"])
        batch.drop_column("public_id")
    op.drop_table("namespace")
