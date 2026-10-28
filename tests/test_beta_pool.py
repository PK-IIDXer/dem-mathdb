"""Actual QueuePool exhaustion must precede SQL and leave writes unchanged."""
import asyncio
from uuid import UUID

import pytest
from sqlalchemy import event, select, func

from dem.api import DemApi
from dem.db.models.tag import Tag
from beta2_support import base_api
from beta_fixture import base_phase
from beta_http import asgi_request
from webapi import beta, deps
from webapi.main import app

SEED_PHASE = base_phase()
SEED_DATABASE = "sqlite"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("cached_capacity", [False, True])
def test_pool_timeout_is_atomic_and_beta_only(base_api, monkeypatch, enabled, cached_capacity):
    own = DemApi.from_url(str(base_api.engine.url), connect_args={"check_same_thread": False},
                          pool_size=1, max_overflow=0, pool_timeout=.03)
    context = deps.WorkspaceRequestContext(UUID(int=0), "test", None, "local.workspace", own)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[deps.get_workspace_request_context] = lambda: context
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    if cached_capacity:
        assert not beta.runtime.is_full(own.engine, beta.Limits())
    def count():
        with own.session() as dem:
            return dem.session.scalar(select(func.count()).select_from(Tag))
    before = count()
    statements = []
    def sql(*args):
        statements.append(args[2])
    try:
        with own.engine.connect():
            event.listen(own.engine, "before_cursor_execute", sql)
            try:
                status, body, headers = asyncio.run(asgi_request(app, "POST", "/tags", {"name":"pool-exhaustion"},
                                                                 raise_app_exceptions=False))
                with monkeypatch.context() as health_context:
                    health_context.setattr(deps, "get_workspace_request_context", lambda *args: context)
                    health_status, health_body, health_headers = asyncio.run(asgi_request(app, "GET", "/health/ready"))
            finally:
                event.remove(own.engine, "before_cursor_execute", sql)
        assert not statements
        assert health_status == 503
        assert count() == before
        if enabled:
            assert status == 503 and body["code"] == "beta.database_busy"
            assert dict(headers)[b"retry-after"] == b"2"
            assert health_body == {"status":"unavailable","code":"beta.database_busy"}
            assert health_headers[b"retry-after"] == b"2"
        else:
            assert status == 500 and "beta.database_busy" not in str(body)
            assert health_body == {"status":"unavailable"} and b"retry-after" not in health_headers
        status, _, _ = asyncio.run(asgi_request(app, "POST", "/tags", {"name":"after-pool-exhaustion"}))
        assert status == 201 and count() == before + 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        own.engine.dispose()


@pytest.mark.parametrize("enabled", [False, True])
def test_engine_checkout_timeout_is_short_only_in_beta(base_api, monkeypatch, enabled):
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    cache = deps.WorkspaceApiCache()
    try:
        engine = cache.get("probe", str(base_api.engine.url)).engine
        assert engine.pool.timeout() == (beta.BETA_POOL_TIMEOUT_SECONDS if enabled else 30)
        assert engine.pool.size() == 5 and engine.pool._max_overflow == 10
    finally:
        cache.close()
