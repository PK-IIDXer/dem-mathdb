"""Acceptance tests for offline upgrades of existing workspace databases."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from dem.api import DemApi
from dem.types import (
    AssumptionStepInput,
    ImplicationIntroStepInput,
    SymbolTypeName,
    Token,
)
from scripts.build_workspace_template import build_workspace_template
from webapi.deps import (
    DEVELOPMENT_ACCOUNT_ID,
    RequestAccount,
    _workspace_api_cache,
    close_database_connections,
    get_dem_api,
    initialize_on_startup,
)
from webapi.management.database import (
    create_management_engine,
    upgrade_management_schema,
)
from webapi.management.deployment_lock import (
    DeploymentLock,
    DeploymentLockBusy,
    deployment_lock_path,
)
from webapi.management.models import Account, Workspace
from webapi.management.schema_revision import (
    content_schema_head,
    upgrade_content_schema,
)
from webapi.management.schema_upgrade import upgrade_all_workspaces
from webapi.management.sqlite_workspace import (
    EXPECTED_SQLITE_TRIGGERS,
    LEGACY_SCHEMA_REVISION,
    LEGACY_SCHEMA_SIGNATURE,
    inspect_sqlite_workspace,
    pending_backup_path,
    schema_signature,
    sha256_file,
)
from webapi.management.workspace import production_fingerprint


SEED_DATABASE = "sqlite"
LEGACY_SQL = Path(__file__).with_name("fixtures") / "public-legacy.sql"
POSTGRES_ADMIN_URL = make_url(
    "postgresql+psycopg://dem_dev@localhost:5432/postgres"
)


def _sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def _register_workspace(management_path: Path, workspace_path: Path):
    management_url = _sqlite_url(management_path)
    upgrade_management_schema(management_url)
    engine = create_management_engine(management_url)
    workspace_id = uuid4()
    with Session(engine) as session, session.begin():
        account = session.get(Account, DEVELOPMENT_ACCOUNT_ID)
        if account is None:
            session.add(
                Account(
                    id=DEVELOPMENT_ACCOUNT_ID,
                    external_subject="development:single-account",
                    email=None,
                    display_name="Development account",
                )
            )
        session.add(
            Workspace(
                id=workspace_id,
                account_id=DEVELOPMENT_ACCOUNT_ID,
                slug=f"workspace-{workspace_id}",
                title="Legacy workspace",
                visibility="public",
                storage_uri=_sqlite_url(workspace_path),
            )
        )
    engine.dispose()
    return management_url, workspace_id


def _workspace_row(management_url: str, workspace_id):
    engine = create_management_engine(management_url)
    try:
        with Session(engine) as session:
            row = session.get(Workspace, workspace_id)
            assert row is not None
            return {
                "state": row.schema_state,
                "revision": row.schema_revision,
                "error": row.schema_error,
                "fingerprint": row.template_fingerprint,
            }
    finally:
        engine.dispose()


def _copy_legacy(tmp_path: Path, name: str = "workspace.db") -> Path:
    destination = tmp_path / name
    with sqlite3.connect(destination) as connection:
        connection.executescript(LEGACY_SQL.read_text(encoding="utf-8"))
    return destination


def _request(workspace_id):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/symbols",
            "headers": [(b"x-workspace-id", str(workspace_id).encode())],
        }
    )


@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch):
    close_database_connections()
    monkeypatch.delenv("DEM_MANAGEMENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DEM_WORKSPACE_TEMPLATE_PATH", raising=False)
    monkeypatch.delenv("DEM_WORKSPACE_DEPLOYMENT_LOCK_PATH", raising=False)
    yield
    close_database_connections()


def test_independent_legacy_fixture_matches_known_revision_schema(tmp_path: Path):
    import hashlib
    assert hashlib.sha256(LEGACY_SQL.read_bytes()).hexdigest() == "3d5dabf4f6429adb6dbaab2ffa2baae8aff75be5df84d951226966dec5ce8486"
    fixture = _copy_legacy(tmp_path, "unversioned.db")
    inspection = inspect_sqlite_workspace(fixture)
    assert inspection.revision is None
    assert inspection.schema_signature == LEGACY_SCHEMA_SIGNATURE
    with closing(sqlite3.connect(fixture)) as connection:
        assert {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("symbol", "formula", "theorem", "proof", "proof_step")
        } == {
            "symbol": 18,
            "formula": 20,
            "theorem": 5,
            "proof": 6,
            "proof_step": 20,
        }

    migrated = tmp_path / "known-revision.db"
    upgrade_content_schema(_sqlite_url(migrated), LEGACY_SCHEMA_REVISION)
    assert schema_signature(migrated) == LEGACY_SCHEMA_SIGNATURE


def test_management_schema_state_migration_on_selected_dialect(tmp_path: Path):
    if os.environ.get("DEM_TEST_DATABASE", "sqlite").lower() == "sqlite":
        database_url = _sqlite_url(tmp_path / "management-dialect.db")
        cleanup = None
    else:
        database_name = f"workspace_management_{os.getpid()}_{uuid4().hex[:8]}"
        admin = create_engine(
            POSTGRES_ADMIN_URL,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        with admin.connect() as connection:
            connection.exec_driver_sql(
                f'CREATE DATABASE "{database_name}" TEMPLATE template0 '
                "STRATEGY = file_copy"
            )
        database_url = POSTGRES_ADMIN_URL.set(database=database_name).render_as_string(
            hide_password=False
        )

        def cleanup():
            with admin.connect() as connection:
                connection.exec_driver_sql(
                    f'DROP DATABASE "{database_name}" WITH (FORCE)'
                )
            admin.dispose()

    try:
        upgrade_management_schema(database_url)
        engine = create_management_engine(database_url)
        try:
            columns = {
                column["name"]
                for column in inspect(engine).get_columns("workspace")
            }
            assert {
                "template_fingerprint",
                "schema_revision",
                "schema_state",
                "schema_error",
                "schema_checked_at",
            } <= columns
        finally:
            engine.dispose()
    finally:
        if cleanup is not None:
            cleanup()


def test_dry_run_identifies_legacy_schema_and_blocks_unknown_shape(tmp_path: Path):
    legacy = _copy_legacy(tmp_path, "legacy.db")
    management_url, legacy_id = _register_workspace(tmp_path / "management.db", legacy)

    result = upgrade_all_workspaces(management_url, dry_run=True)[0]
    assert result.workspace_id == legacy_id
    assert result.outcome == "would_upgrade"
    assert f"legacy={LEGACY_SCHEMA_REVISION}" in result.detail
    assert inspect_sqlite_workspace(legacy).revision is None

    unknown = _copy_legacy(tmp_path, "unknown.db")
    with closing(sqlite3.connect(unknown)) as connection:
        connection.execute(
            "CREATE TABLE unexpected_schema_change (id INTEGER PRIMARY KEY)"
        )
    _, unknown_id = _register_workspace(tmp_path / "management.db", unknown)
    results = upgrade_all_workspaces(
        management_url, dry_run=True, workspace_ids={unknown_id}
    )
    assert results[0].outcome == "upgrade_blocked"
    row = _workspace_row(management_url, unknown_id)
    assert row["state"] == "upgrade_blocked"
    assert json.loads(row["error"])["code"] == "unknown_legacy_schema"
    assert inspect_sqlite_workspace(unknown).revision is None


def test_upgrade_reaches_head_and_preserves_existing_content(tmp_path: Path):
    workspace = _copy_legacy(tmp_path)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )
    with closing(sqlite3.connect(workspace)) as connection:
        before = {
            "counts": {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "namespace",
                    "symbol",
                    "formula",
                    "definition",
                    "axiom",
                    "theorem",
                    "proof",
                )
            },
            "public_ids": {
                table: list(
                    connection.execute(f"SELECT public_id FROM {table} ORDER BY id")
                )
                for table in (
                    "symbol",
                    "definition",
                    "axiom",
                    "theorem",
                    "proof",
                )
            },
            "formula_hashes": list(
                connection.execute("SELECT hash FROM formula ORDER BY id")
            ),
            "proof_statuses": list(
                connection.execute("SELECT status FROM proof ORDER BY id")
            ),
        }

    result = upgrade_all_workspaces(management_url)[0]
    assert result.outcome == "upgraded"
    inspection = inspect_sqlite_workspace(workspace)
    assert inspection.revision == content_schema_head()
    assert inspection.quick_check == "ok"
    assert inspection.incomplete_formulas == ()
    assert inspection.triggers == EXPECTED_SQLITE_TRIGGERS
    with closing(sqlite3.connect(workspace)) as connection:
        assert list(
            connection.execute("SELECT code FROM formula_type ORDER BY id")
        ) == [("term",), ("proposition",)]
        after = {
            "counts": {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before["counts"]
            },
            "public_ids": {
                table: list(
                    connection.execute(f"SELECT public_id FROM {table} ORDER BY id")
                )
                for table in before["public_ids"]
            },
            "formula_hashes": list(
                connection.execute("SELECT hash FROM formula ORDER BY id")
            ),
            "proof_statuses": list(
                connection.execute("SELECT status FROM proof ORDER BY id")
            ),
        }
    assert after == before
    with closing(sqlite3.connect(workspace)) as connection:
        # 20260923_0001: every existing axiom was born in dem.foundation.logic.
        assert connection.execute(
            "SELECT DISTINCT namespace.name FROM axiom "
            "JOIN namespace ON namespace.id = axiom.namespace_id"
        ).fetchall() == [("dem.foundation.logic",)]
        assert connection.execute(
            "SELECT DISTINCT namespace.name FROM axiom_system "
            "JOIN namespace ON namespace.id = axiom_system.namespace_id"
        ).fetchall() == [("dem.foundation.logic",)]
    row = _workspace_row(management_url, workspace_id)
    assert row == {
        "state": "ready",
        "revision": content_schema_head(),
        "error": None,
        "fingerprint": production_fingerprint(),
    }
    assert upgrade_all_workspaces(management_url)[0].outcome == "ready"


def test_upgraded_legacy_workspace_supports_current_authoring(tmp_path: Path):
    workspace = _copy_legacy(tmp_path)
    management_url, _ = _register_workspace(tmp_path / "management.db", workspace)
    assert upgrade_all_workspaces(management_url)[0].outcome == "upgraded"

    api = DemApi.from_url(_sqlite_url(workspace))
    try:
        with api.transaction() as dem:
            assert dem.symbols.list_all()
            prop_type = dem.symbols.get_symbol_type_by_name(
                SymbolTypeName.FREE_PROP_VAR.value
            )
            symbol = dem.symbols.register("upgraded_workspace_p", prop_type.id, 0)
            atom = dem.formulas.register([Token(symbol_id=symbol.id)])
            implication = dem.symbols.get_by_role("implication")
            statement = dem.formulas.register(
                [
                    Token(symbol_id=implication.id),
                    Token(symbol_id=symbol.id),
                    Token(symbol_id=symbol.id),
                ]
            )
            theorem = dem.theorems.register(
                "upgraded_workspace_self_implication", statement.id
            )
            proof = dem.proofs.create_proof(theorem.id)
            dem.proofs.add_step(proof.id, AssumptionStepInput(), atom.id)
            dem.proofs.add_step(proof.id, ImplicationIntroStepInput(0, 0))
            dem.proofs.validate(proof.id)
            assert dem.proofs.get(proof.id).status == "verified"
    finally:
        api.engine.dispose()


FAULT_POINTS = (
    "after_stamp",
    "after_migration:20260918_0001",
    "after_migration:20260918_0002",
    "after_migration:20260918_0003",
    "after_migration:20260918_0004",
    "after_migration:20260918_0005",
    "after_migration:20260923_0001",
    "after_migration:20260923_0002",
    "after_migration:20260923_0003",
    "after_postflight",
    "before_publish",
)


@pytest.mark.parametrize("fault_point", FAULT_POINTS)
def test_fault_before_publish_keeps_original_and_recoverable_backup(
    tmp_path: Path, fault_point: str
):
    workspace = _copy_legacy(tmp_path)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )
    original_hash = sha256_file(workspace)

    def inject(point, _workspace_id):
        if point == fault_point:
            raise RuntimeError(f"injected at {point}")

    result = upgrade_all_workspaces(
        management_url, fault_injector=inject
    )[0]
    assert result.outcome == "upgrade_blocked"
    assert sha256_file(workspace) == original_hash
    backup = pending_backup_path(workspace, workspace_id)
    assert backup.is_file()
    restored = tmp_path / "restored.db"
    shutil.copyfile(backup, restored)
    assert sha256_file(restored) == original_hash


def test_incomplete_workspace_is_blocked_and_never_cached(tmp_path: Path, monkeypatch):
    workspace = _copy_legacy(tmp_path)
    with closing(sqlite3.connect(workspace)) as connection:
        formula_id = connection.execute(
            "SELECT id FROM formula WHERE token_count > 0 ORDER BY id LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "DELETE FROM formula_token WHERE formula_id=? AND position=("
            "SELECT MAX(position) FROM formula_token WHERE formula_id=?)",
            (formula_id, formula_id),
        )
        connection.commit()
    original_hash = sha256_file(workspace)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )
    result = upgrade_all_workspaces(management_url)[0]
    assert result.outcome == "upgrade_blocked"
    assert sha256_file(workspace) == original_hash
    error = json.loads(_workspace_row(management_url, workspace_id)["error"])
    assert error["code"] == "incomplete_formula"
    assert error["formula_id"] == formula_id

    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)
    with pytest.raises(HTTPException) as exc_info:
        get_dem_api(_request(workspace_id), RequestAccount(DEVELOPMENT_ACCOUNT_ID))
    assert exc_info.value.status_code == 503
    assert len(_workspace_api_cache) == 0


def test_malformed_formula_records_stable_error_and_formula_id(tmp_path: Path):
    workspace = _copy_legacy(tmp_path)
    with closing(sqlite3.connect(workspace)) as connection:
        formula_id = connection.execute(
            "SELECT id FROM formula WHERE token_count > 0 ORDER BY id LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "UPDATE formula_token SET symbol_id=NULL, de_bruijn_index=999 "
            "WHERE formula_id=? AND position=0",
            (formula_id,),
        )
        connection.commit()
    original_hash = sha256_file(workspace)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )

    result = upgrade_all_workspaces(management_url)[0]
    assert result.outcome == "upgrade_blocked"
    assert sha256_file(workspace) == original_hash
    error = json.loads(_workspace_row(management_url, workspace_id)["error"])
    assert error["code"] == "formula_not_well_formed"
    assert error["formula_id"] == formula_id


def test_api_shared_lock_blocks_upgrade_until_shutdown(tmp_path: Path, monkeypatch):
    template = tmp_path / "template.db"
    build_workspace_template(template)
    workspace = tmp_path / "workspace.db"
    shutil.copyfile(template, workspace)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )
    engine = create_management_engine(management_url)
    with Session(engine) as session, session.begin():
        row = session.get(Workspace, workspace_id)
        row.schema_state = "ready"
        row.schema_revision = content_schema_head()
    engine.dispose()
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)
    monkeypatch.setenv("DEM_WORKSPACE_TEMPLATE_PATH", str(template))

    initialize_on_startup()
    get_dem_api(_request(workspace_id), RequestAccount(DEVELOPMENT_ACCOUNT_ID))
    with pytest.raises(DeploymentLockBusy):
        upgrade_all_workspaces(management_url)
    assert inspect_sqlite_workspace(workspace).revision == content_schema_head()
    close_database_connections()
    assert upgrade_all_workspaces(management_url)[0].outcome == "ready"


def test_api_startup_rejects_exclusive_upgrade_lock(tmp_path: Path, monkeypatch):
    template = tmp_path / "template.db"
    build_workspace_template(template)
    management_url = _sqlite_url(tmp_path / "management.db")
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)
    monkeypatch.setenv("DEM_WORKSPACE_TEMPLATE_PATH", str(template))

    with DeploymentLock(deployment_lock_path(management_url), exclusive=True):
        with pytest.raises(DeploymentLockBusy):
            initialize_on_startup()


_LOCK_PROBE = """
import sys
from pathlib import Path
from webapi.management.deployment_lock import DeploymentLock, DeploymentLockBusy
try:
    DeploymentLock(Path(sys.argv[1]), exclusive=sys.argv[2] == "exclusive").acquire()
except DeploymentLockBusy:
    print("busy")
else:
    print("acquired")
"""


def _probe_lock(lock_path: Path, mode: str) -> str:
    import subprocess
    import sys

    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", _LOCK_PROBE, str(lock_path), mode],
        capture_output=True,
        check=True,
        cwd=repository,
        env={**os.environ, "PYTHONPATH": str(repository)},
        text=True,
    )
    return completed.stdout.strip()


def test_shared_deployment_locks_coexist_across_processes(tmp_path: Path) -> None:
    """Several API processes must be able to hold the shared lock at once.

    On Windows ``msvcrt.locking`` has no shared mode, so the lock is taken with
    ``LockFileEx``; this pins that a second process really shares it.
    """
    lock_path = tmp_path / "deployment.lock"
    with DeploymentLock(lock_path, exclusive=False):
        assert _probe_lock(lock_path, "shared") == "acquired"
        assert _probe_lock(lock_path, "exclusive") == "busy"
    assert _probe_lock(lock_path, "exclusive") == "acquired"
    with DeploymentLock(lock_path, exclusive=True):
        assert _probe_lock(lock_path, "shared") == "busy"


def test_single_database_startup_takes_no_deployment_lock(
    tmp_path: Path, monkeypatch
) -> None:
    """The legacy single-DB mode has no workspace DBs, so it must not lock."""
    import webapi.deps as deps

    monkeypatch.delenv("DEM_MANAGEMENT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DEM_DATABASE_URL", _sqlite_url(tmp_path / "single.db"))
    try:
        initialize_on_startup()
        assert deps._deployment_lock is None
    finally:
        close_database_connections()


def test_cache_admission_rejects_incomplete_head_workspace(
    tmp_path: Path, monkeypatch
):
    template = tmp_path / "template.db"
    build_workspace_template(template)
    workspace = tmp_path / "workspace.db"
    shutil.copyfile(template, workspace)
    with closing(sqlite3.connect(workspace)) as connection:
        formula_id = connection.execute(
            "SELECT id FROM formula WHERE token_count > 0 ORDER BY id LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "DROP TRIGGER formula_token_delete_incomplete_only"
        )
        connection.execute(
            "DELETE FROM formula_token WHERE formula_id=? AND position=("
            "SELECT MAX(position) FROM formula_token WHERE formula_id=?)",
            (formula_id, formula_id),
        )
        connection.commit()
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )
    engine = create_management_engine(management_url)
    with Session(engine) as session, session.begin():
        row = session.get(Workspace, workspace_id)
        row.schema_state = "ready"
        row.schema_revision = content_schema_head()
    engine.dispose()
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", management_url)

    with pytest.raises(HTTPException) as exc_info:
        get_dem_api(_request(workspace_id), RequestAccount(DEVELOPMENT_ACCOUNT_ID))
    assert exc_info.value.status_code == 503
    assert len(_workspace_api_cache) == 0


def test_post_publish_crash_converges_management_row_on_dry_run(tmp_path: Path):
    workspace = _copy_legacy(tmp_path)
    management_url, workspace_id = _register_workspace(
        tmp_path / "management.db", workspace
    )

    def crash(point, _workspace_id):
        if point == "after_publish":
            raise SimulatedCrash

    with pytest.raises(SimulatedCrash):
        upgrade_all_workspaces(management_url, fault_injector=crash)
    assert inspect_sqlite_workspace(workspace).revision == content_schema_head()
    assert _workspace_row(management_url, workspace_id)["state"] == "upgrading"

    result = upgrade_all_workspaces(management_url, dry_run=True)[0]
    assert result.outcome == "ready"
    row = _workspace_row(management_url, workspace_id)
    assert row["state"] == "ready"
    assert row["revision"] == content_schema_head()


class SimulatedCrash(BaseException):
    pass
