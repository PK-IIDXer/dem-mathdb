"""SQLite file operations used by the workspace schema state machine."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from dem.db.triggers import (
    INCOMPLETE_FORMULAS_SQL,
    SQLITE_TIER_B_TRIGGER_SPECS,
    TIER_A_TRIGGER_SPECS,
    TIER_B_IMMUTABILITY_TRIGGER_SPECS,
)
from webapi.management.workspace import embedded_schema_revision


LEGACY_SCHEMA_REVISION = "20260910_0002"
# Digest of the normalized create_all schema at LEGACY_SCHEMA_REVISION. Tests also compare the
# committed legacy fixture against a database migrated to LEGACY_SCHEMA_REVISION.
LEGACY_SCHEMA_SIGNATURE = (
    "c0db81e0f9e184b92a31182b9d29651eaff0f4490c5a6a65954e534573c91c74"
)

EXPECTED_SQLITE_TRIGGERS = frozenset(
    spec.name
    for spec in (
        *TIER_A_TRIGGER_SPECS,
        *SQLITE_TIER_B_TRIGGER_SPECS,
        *TIER_B_IMMUTABILITY_TRIGGER_SPECS,
    )
)


@dataclass(frozen=True)
class SQLiteInspection:
    revision: str | None
    schema_signature: str
    quick_check: str
    incomplete_formulas: tuple[tuple[int, int, int], ...]
    triggers: frozenset[str]


def sqlite_path_from_url(storage_uri: str) -> Path:
    url = make_url(storage_uri)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError(f"workspace storage is not a SQLite file: {storage_uri}")
    if url.database == ":memory:":
        raise ValueError("in-memory SQLite is not a workspace file")
    return Path(url.database).resolve()


def _normalized_sql(sql: str | None) -> str | None:
    if sql is None:
        return None
    return re.sub(r"\s+", " ", sql.strip()).lower()


def _normalized_default(value: object, type_name: str) -> str:
    normalized = _normalized_sql(str(value)) or ""
    if type_name in {"integer", "bigint", "smallint"}:
        integer = re.fullmatch(
            r"'?(-?\d+)'?(?:::(?:smallint|integer|bigint))?", normalized
        )
        if integer is not None:
            return integer.group(1)
    return normalized


def schema_signature(path: Path) -> str:
    """Return the normalized table/constraint/index/trigger schema signature."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    engine = create_engine(
        "sqlite+pysqlite://",
        creator=lambda: sqlite3.connect(uri, uri=True),
    )
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names()) - {"alembic_version"}
        signature: dict[str, object] = {
            "tables": sorted(tables),
            "columns": sorted(
                (
                    table,
                    column["name"],
                    str(column["type"]).lower(),
                    column["nullable"],
                    (
                        _normalized_default(
                            column["default"], str(column["type"]).lower()
                        )
                        if column.get("default") is not None
                        else None
                    ),
                )
                for table in tables
                for column in inspector.get_columns(table)
            ),
            "primary_keys": sorted(
                (table, *inspector.get_pk_constraint(table)["constrained_columns"])
                for table in tables
            ),
            "foreign_keys": sorted(
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
            ),
            "unique_constraints": sorted(
                (table, *constraint["column_names"])
                for table in tables
                for constraint in inspector.get_unique_constraints(table)
            ),
            "check_constraints": sorted(
                (table, _normalized_sql(constraint["sqltext"]))
                for table in tables
                for constraint in inspector.get_check_constraints(table)
            ),
            "indexes": sorted(
                (table, bool(index["unique"]), *index["column_names"])
                for table in tables
                for index in inspector.get_indexes(table)
            ),
        }
        with engine.connect() as connection:
            signature["triggers"] = sorted(
                (str(name), str(table), _normalized_sql(str(sql)))
                for name, table, sql in connection.exec_driver_sql(
                    "SELECT name, tbl_name, sql FROM sqlite_master "
                    "WHERE type='trigger' ORDER BY name"
                )
            )
    finally:
        engine.dispose()
    encoded = json.dumps(signature, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def inspect_sqlite_workspace(path: Path) -> SQLiteInspection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        revision = embedded_schema_revision(connection)
        quick_row = connection.execute("PRAGMA quick_check").fetchone()
        quick_check = "missing result" if quick_row is None else str(quick_row[0])
        signature = schema_signature(path)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if {"formula", "formula_token"} <= tables:
            incomplete = tuple(
                (int(row[0]), int(row[1]), int(row[2]))
                for row in connection.execute(INCOMPLETE_FORMULAS_SQL)
            )
        else:
            incomplete = ()
        triggers = frozenset(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        )
    return SQLiteInspection(revision, signature, quick_check, incomplete, triggers)


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)
            quick_check = destination_connection.execute(
                "PRAGMA quick_check"
            ).fetchone()
            if quick_check != ("ok",):
                raise RuntimeError(f"SQLite backup failed quick_check: {destination}")
    # The deployment is offline and the source has no live WAL writers.  Keep a
    # byte-identical recovery image after the Backup API has proved the snapshot
    # can be materialized; fault tests and operators can then verify SHA-256.
    shutil.copyfile(source, destination)


def basic_read_smoke(path: Path) -> None:
    """Exercise the joins that made old workspaces unreadable by the current ORM."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute(
            "SELECT symbol.id, output_type.code "
            "FROM symbol "
            "JOIN symbol_type ON symbol_type.id = symbol.symbol_type_id "
            "JOIN formula_type AS output_type "
            "ON output_type.id = symbol_type.output_formula_type_id "
            "ORDER BY symbol.id LIMIT 1"
        ).fetchone()


def workspace_backup_path(workspace_path: Path, workspace_id: UUID) -> Path:
    return workspace_path.parent / ".schema-backups" / f"{workspace_id}.db"


def pending_backup_path(workspace_path: Path, workspace_id: UUID) -> Path:
    return workspace_backup_path(workspace_path, workspace_id).with_suffix(
        ".pending.db"
    )


def workspace_shadow_path(workspace_path: Path, workspace_id: UUID) -> Path:
    return workspace_path.with_name(
        f".{workspace_path.name}.{workspace_id}.schema-shadow"
    )


def publish_shadow(shadow: Path, workspace_path: Path) -> None:
    os.replace(shadow, workspace_path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
