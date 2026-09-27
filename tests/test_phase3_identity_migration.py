from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from dem.identity import DEFAULT_NAMESPACE_NAME, deterministic_public_id


def migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20260910_0002_phase3_identity_namespace.py"
    )
    spec = importlib.util.spec_from_file_location("phase3_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_identity_namespace_migration_preserves_rows_and_hash_granularity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    change = migration()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE symbol (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "namespace_id INTEGER, CONSTRAINT uq_symbol_name UNIQUE (name))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE formula (id INTEGER PRIMARY KEY, hash TEXT NOT NULL UNIQUE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE formula_token (formula_id INTEGER, position INTEGER, "
            "symbol_id INTEGER, de_bruijn_index INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE axiom (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE definition (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "new_symbol_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE theorem (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "CONSTRAINT uq_theorem_name UNIQUE (name))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE proof (id INTEGER PRIMARY KEY, theorem_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql("INSERT INTO symbol VALUES (1, 'p', NULL), (2, 'q', NULL)")
        connection.exec_driver_sql("INSERT INTO formula VALUES (1, 'old-a'), (2, 'old-b')")
        connection.exec_driver_sql(
            "INSERT INTO formula_token VALUES (1, 0, 1, NULL), (2, 0, 2, NULL)"
        )
        connection.exec_driver_sql("INSERT INTO axiom VALUES (1, 'axiom-a')")
        connection.exec_driver_sql("INSERT INTO definition VALUES (1, 'definition-a', 1)")
        connection.exec_driver_sql("INSERT INTO theorem VALUES (1, 'result')")
        connection.exec_driver_sql("INSERT INTO proof VALUES (1, 1), (2, 1)")
        with Operations.context(MigrationContext.configure(connection)):
            change.upgrade()
            new_hashes = connection.exec_driver_sql(
                "SELECT hash FROM formula ORDER BY id"
            ).scalars().all()
            assert len(new_hashes) == len(set(new_hashes)) == 2
            assert set(new_hashes).isdisjoint({"old-a", "old-b"})
            symbol_ids = connection.exec_driver_sql(
                "SELECT public_id FROM symbol ORDER BY id"
            ).scalars().all()
            assert symbol_ids == [
                deterministic_public_id("symbol", f"{DEFAULT_NAMESPACE_NAME}::p"),
                deterministic_public_id("symbol", f"{DEFAULT_NAMESPACE_NAME}::q"),
            ]
            assert connection.exec_driver_sql(
                "SELECT public_id FROM formula ORDER BY id"
            ).scalars().all() == [
                deterministic_public_id("formula", formula_hash)
                for formula_hash in new_hashes
            ]
            assert connection.exec_driver_sql(
                "SELECT public_id FROM axiom"
            ).scalar_one() == deterministic_public_id(
                "axiom", f"{DEFAULT_NAMESPACE_NAME}::axiom-a"
            )
            assert connection.exec_driver_sql(
                "SELECT public_id FROM definition"
            ).scalar_one() == deterministic_public_id(
                "definition", f"{DEFAULT_NAMESPACE_NAME}::definition-a"
            )
            theorem_public_id = deterministic_public_id(
                "theorem", f"{DEFAULT_NAMESPACE_NAME}::result"
            )
            assert connection.exec_driver_sql(
                "SELECT public_id FROM theorem"
            ).scalar_one() == theorem_public_id
            assert connection.exec_driver_sql(
                "SELECT public_id, identity_ordinal FROM proof ORDER BY id"
            ).all() == [
                (deterministic_public_id("proof", f"{theorem_public_id}::0"), 0),
                (deterministic_public_id("proof", f"{theorem_public_id}::1"), 1),
            ]
            assert connection.exec_driver_sql(
                "SELECT theorem_id, next_ordinal FROM proof_identity_sequence"
            ).all() == [(1, 2)]
            for table in ("symbol", "formula", "axiom", "definition", "theorem", "proof"):
                values = connection.exec_driver_sql(
                    f"SELECT public_id FROM {table}"
                ).scalars().all()
                assert values and all(str(UUID(value)) == value for value in values)
            assert connection.exec_driver_sql(
                "SELECT namespace_id FROM symbol"
            ).scalars().all() == [2, 2]
            change.downgrade()
        assert "public_id" not in {
            column["name"] for column in inspect(connection).get_columns("symbol")
        }
        assert "proof_identity_sequence" not in inspect(connection).get_table_names()
    engine.dispose()
