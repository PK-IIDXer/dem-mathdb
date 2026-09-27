"""Alembic history integration contracts."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from dem.db.models import Base


SCHEMA_FEATURES = (
    "tables",
    "columns",
    "primary_keys",
    "foreign_keys",
    "unique_constraints",
    "check_constraints",
    "indexes",
    "sequences",
    "triggers",
)
_TEST_DATABASE_ENV = "DEM_TEST_DATABASE"
_DATABASE_URL_ENV = "DEM_DATABASE_URL"
_POSTGRES_ADMIN_URL = make_url(
    "postgresql+psycopg://dem_dev@localhost:5432/postgres"
)


def _normalized_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _normalized_default(value: object, type_name: str) -> str:
    normalized = _normalized_sql(str(value))
    if type_name in {"integer", "bigint", "smallint"}:
        integer = re.fullmatch(
            r"'?(-?\d+)'?(?:::(?:smallint|integer|bigint))?", normalized
        )
        if integer is not None:
            return integer.group(1)
    return normalized


def _schema_signature(engine) -> dict[str, set[tuple[object, ...]]]:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    return {
        "tables": {(table,) for table in tables},
        "columns": {
            (
                table,
                column["name"],
                str(column["type"]).lower(),
                column["nullable"],
                (
                    _normalized_default(column["default"], str(column["type"]).lower())
                    if column.get("default") is not None
                    else None
                ),
            )
            for table in tables
            for column in inspector.get_columns(table)
        },
        "primary_keys": {
            (table, *inspector.get_pk_constraint(table)["constrained_columns"])
            for table in tables
        },
        "foreign_keys": {
            (
                table,
                *constraint["constrained_columns"],
                "->",
                constraint["referred_table"],
                *constraint["referred_columns"],
                "ondelete",
                (constraint.get("options") or {}).get("ondelete"),
            )
            for table in tables
            for constraint in inspector.get_foreign_keys(table)
        },
        "unique_constraints": {
            (table, *constraint["column_names"])
            for table in tables
            for constraint in inspector.get_unique_constraints(table)
        },
        "check_constraints": {
            (table, _normalized_sql(constraint["sqltext"]))
            for table in tables
            for constraint in inspector.get_check_constraints(table)
        },
        "indexes": {
            (table, bool(index["unique"]), *index["column_names"])
            for table in tables
            for index in inspector.get_indexes(table)
        },
        "sequences": (
            {(sequence,) for sequence in inspector.get_sequence_names()}
            if engine.dialect.name == "postgresql"
            else set()
        ),
        "triggers": _trigger_signature(engine),
    }


def _trigger_signature(engine: Engine) -> set[tuple[object, ...]]:
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            rows = connection.execute(
                text(
                    "SELECT name, tbl_name, sql FROM sqlite_master "
                    "WHERE type = 'trigger' ORDER BY name"
                )
            )
            result = set()
            for name, table, sql in rows:
                match = re.search(
                    r"\b(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\b",
                    sql,
                    re.IGNORECASE,
                )
                assert match is not None, sql
                result.add((name, table, match.group(1).upper(), match.group(2).upper()))
            return result
        rows = connection.execute(
            text(
                "SELECT trigger.tgname, relation.relname, trigger.tgtype "
                "FROM pg_trigger AS trigger "
                "JOIN pg_class AS relation ON relation.oid = trigger.tgrelid "
                "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                "WHERE NOT trigger.tgisinternal "
                "AND namespace.nspname = current_schema() "
                "ORDER BY trigger.tgname"
            )
        )
        result = set()
        for name, table, trigger_type in rows:
            timing = "BEFORE" if trigger_type & 2 else "AFTER"
            events = (
                ("INSERT", 4),
                ("DELETE", 8),
                ("UPDATE", 16),
                ("TRUNCATE", 32),
            )
            for event_name, mask in events:
                if trigger_type & mask:
                    result.add((name, table, timing, event_name))
        return result


def _schema_difference(
    migration: dict[str, set[tuple[object, ...]]],
    model: dict[str, set[tuple[object, ...]]],
) -> dict[str, dict[str, set[tuple[object, ...]]]]:
    return {
        feature: {
            "migration_only": migration[feature] - model[feature],
            "model_only": model[feature] - migration[feature],
        }
        for feature in SCHEMA_FEATURES
        if migration[feature] != model[feature]
    }


KNOWN_SCHEMA_DIFFERENCES: dict[str, dict[str, set[tuple[object, ...]]]] = {
    "tables": {
        "migration_only": {("alembic_version",)},
        "model_only": set(),
    },
    "columns": {
        "migration_only": {
            ("alembic_version", "version_num", "varchar(32)", False, None)
        },
        "model_only": set(),
    },
    "primary_keys": {
        "migration_only": {("alembic_version", "version_num")},
        "model_only": set(),
    },
}


def _alembic_config(database_url) -> Config:
    repository = Path(__file__).resolve().parents[1]
    config = Config(str(repository / "alembic.ini"))
    config.set_main_option("script_location", str(repository / "alembic"))
    config.set_main_option(
        "sqlalchemy.url", database_url.render_as_string(hide_password=False)
    )
    return config


def _migrate(database_url, revision: str) -> None:
    rendered_url = database_url.render_as_string(hide_password=False)
    with patch.dict(os.environ, {_DATABASE_URL_ENV: rendered_url}):
        if revision == "base":
            command.downgrade(_alembic_config(database_url), revision)
        else:
            command.upgrade(_alembic_config(database_url), revision)


@contextmanager
def _empty_database_pair(tmp_path: Path) -> Iterator[tuple[Engine, Engine]]:
    database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    if database == "sqlite":
        migration_engine = create_engine(
            f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
        )
        model_engine = create_engine(
            f"sqlite+pysqlite:///{(tmp_path / 'model.db').as_posix()}"
        )
        try:
            yield migration_engine, model_engine
        finally:
            migration_engine.dispose()
            model_engine.dispose()
        return
    if database != "postgresql":
        raise RuntimeError(f"unknown test database: {database!r}")

    suffix = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    migration_name = f"stage3_schema_migration_{suffix}"
    model_name = f"stage3_schema_model_{suffix}"
    admin_engine = create_engine(
        _POSTGRES_ADMIN_URL,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    with admin_engine.connect() as connection:
        for name in (migration_name, model_name):
            connection.exec_driver_sql(
                f'CREATE DATABASE "{name}" TEMPLATE template0 STRATEGY = file_copy'
            )
    migration_engine = create_engine(_POSTGRES_ADMIN_URL.set(database=migration_name))
    model_engine = create_engine(_POSTGRES_ADMIN_URL.set(database=model_name))
    try:
        yield migration_engine, model_engine
    finally:
        migration_engine.dispose()
        model_engine.dispose()
        for name in (migration_name, model_name):
            _drop_database_when_released(admin_engine, name)
        admin_engine.dispose()


def _drop_database_when_released(admin_engine: Engine, name: str) -> None:
    """Drop a scratch database, waiting out a transient superuser backend.

    Right after a database is filled, an autovacuum worker (a superuser backend)
    may briefly connect to it. ``DROP DATABASE ... WITH (FORCE)`` then tries to
    terminate that backend, which ``dem_dev`` has no privilege to do, and fails
    with InsufficientPrivilege. The worker leaves within seconds, so retry.
    """
    import time

    from sqlalchemy.exc import ProgrammingError

    deadline = time.monotonic() + 30.0
    while True:
        try:
            with admin_engine.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            return
        except ProgrammingError as error:
            if "InsufficientPrivilege" not in type(error.orig).__name__:
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)


def test_empty_sqlite_database_upgrades_to_head(tmp_path: Path) -> None:
    """The formerly broken SQLite path never completed, so repairing it is safe."""
    database = tmp_path / "empty.db"
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    try:
        _migrate(engine.url, "head")
        with engine.connect() as connection:
            version = connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            assert version == "20260923_0003"
            tables = set(inspect(connection).get_table_names())
            expected = {
                "authoring_provenance",
                "namespace",
                "proof_identity_sequence",
            }
            assert expected <= tables
        with engine.begin() as connection:
            created_at = connection.scalar(
                text(
                    "INSERT INTO formula_type (name, code) VALUES "
                    "('migration-default-smoke', 'term') RETURNING created_at"
                )
            )
            assert created_at is not None

        _migrate(engine.url, "base")
        _migrate(engine.url, "head")
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM alembic_version")
            ) == "20260923_0003"
    finally:
        engine.dispose()


def test_alembic_and_model_schema_differ_only_as_documented(tmp_path: Path) -> None:
    with _empty_database_pair(tmp_path) as (migration_engine, model_engine):
        _migrate(migration_engine.url, "head")
        Base.metadata.create_all(model_engine)
        difference = _schema_difference(
            _schema_signature(migration_engine), _schema_signature(model_engine)
        )

    assert difference == KNOWN_SCHEMA_DIFFERENCES
