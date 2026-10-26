"""Beta startup reads a prepared snapshot; legacy bootstrap remains separate."""
import re
import asyncio
import json

import pytest
from sqlalchemy import Engine, event, text

from beta2_support import base_api  # noqa: F401
from webapi import deps
from webapi.main import app
from beta_http import asgi_request

from beta_fixture import base_phase
SEED_PHASE = base_phase()


@pytest.fixture
def startup(base_api, monkeypatch):
    monkeypatch.setenv("DEM_BETA", "1")
    monkeypatch.delenv("DEM_MANAGEMENT_DATABASE_URL", raising=False)
    monkeypatch.setattr(deps._workspace_api_cache, "get", lambda *a, **k: base_api)
    return base_api


def test_beta_startup_only_selects(startup):
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip())
    event.listen(startup.engine, "before_cursor_execute", capture)
    try:
        deps.initialize_on_startup()
        deps.initialize_on_startup()
    finally:
        event.remove(startup.engine, "before_cursor_execute", capture)
    assert len(statements) >= 6
    assert all(sql.upper().startswith("SELECT") for sql in statements), statements


def test_beta_startup_new_connection_never_bootstraps(startup, monkeypatch):
    cache = deps.WorkspaceApiCache()
    monkeypatch.setattr(deps, "_workspace_api_cache", cache)
    monkeypatch.setenv("DEM_DATABASE_URL", startup.engine.url.render_as_string(hide_password=False))
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip())
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        deps.initialize_on_startup()
    finally:
        event.remove(Engine, "before_cursor_execute", capture)
        cache.close()
    assert statements
    assert not any(re.match(r"(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE|VACUUM|REINDEX)\b", sql, re.I)
                   for sql in statements), statements


def test_beta_startup_rejects_wrong_revision(startup):
    with startup.engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'not-ready'"))
    with pytest.raises(RuntimeError, match="^Beta database startup check failed$"):
        deps.initialize_on_startup()


def test_beta_startup_rejects_incomplete_formula(startup, monkeypatch):
    # Substitute the health query's result, never proof validation or a trigger.
    monkeypatch.setattr(deps, "INCOMPLETE_FORMULAS_SQL", "SELECT 1")
    with pytest.raises(RuntimeError, match="startup check failed"):
        deps.initialize_on_startup()


def test_beta_startup_sanitizes_connection_failure(startup, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("secret password and database address")
    monkeypatch.setattr(deps._workspace_api_cache, "get", fail)
    with pytest.raises(RuntimeError) as error:
        deps.initialize_on_startup()
    assert "secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_beta_startup_refuses_management_before_writes(startup, monkeypatch):
    monkeypatch.setenv("DEM_MANAGEMENT_DATABASE_URL", "sqlite:///unused.db")
    with pytest.raises(RuntimeError, match="startup check failed"):
        deps.initialize_on_startup()


def test_non_beta_bootstraps_as_before(startup, monkeypatch):
    monkeypatch.delenv("DEM_BETA")
    calls = []
    monkeypatch.setattr(startup, "create_schema", lambda: calls.append("schema"))
    monkeypatch.setattr(startup, "seed_core", lambda: calls.append("seed"))
    monkeypatch.setattr(deps, "_database_url", lambda: "sqlite:///unused.db")
    deps.initialize_on_startup()
    assert calls == ["schema", "seed"]


def test_config_reports_reset_error_and_ignores_corruption(startup, tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    monkeypatch.setenv("DEM_BETA_STATUS_FILE", str(status))
    error = status.with_name("reset-error.json")
    def config():
        code, result, _ = asyncio.run(asgi_request(app, "GET", "/config"))
        assert code == 200
        return result
    assert config()["beta"]["last_reset_error"] is None
    expected = {"failed_at": "2026-10-22T01:02:03Z", "stage": "prepare"}
    error.write_text(json.dumps(expected))
    # Reporting the preparation failure must work even without status.json.
    assert config()["beta"]["last_reset_error"] == expected
    status.write_text('{"last_reset_at":"2026-10-21T00:00:00Z","next_reset_at":"2026-10-28T00:00:00Z"}')
    for payload in ("not-json", "[]", "null", "{}", json.dumps(dict(expected, failed_at="bad")),
                    json.dumps(dict(expected, failed_at="2026-10-22T01:02:03")),
                    json.dumps(dict(expected, stage="private internal message")),
                    json.dumps(dict(expected, secret="must not appear"))):
        error.write_text(payload)
        result = config()
        assert result["beta"]["last_reset_error"] is None
        assert result["beta"]["last_reset_at"] == "2026-10-21T00:00:00Z"
    error.write_bytes(b"\xff")
    assert config()["beta"]["last_reset_error"] is None
    error.write_text(json.dumps(expected))
    monkeypatch.delenv("DEM_BETA")
    assert config() == {"read_only": False}
