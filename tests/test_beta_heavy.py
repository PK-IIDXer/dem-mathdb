"""Global beta CPU admission, independent of client rate buckets."""
import asyncio

import pytest

from webapi import beta
from webapi.main import app
from beta_state import patch_state
from beta_http import asgi_request
from test_webapi_request_failures import live_api

from beta_fixture import base_phase
SEED_PHASE = base_phase()


@pytest.fixture
def beta_runtime(request, monkeypatch):
    monkeypatch.setenv("DEM_BETA", "1")
    monkeypatch.delenv("DEM_READ_ONLY", raising=False)
    monkeypatch.delenv("DEM_BETA_FLAG_DIR", raising=False)
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    request.addfinalizer(patch_state(app.state, "beta_limits", beta.Limits()))
    return beta.runtime


def test_global_heavy_limit_across_clients_and_release(beta_runtime):
    async def run():
        entered, finish = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            entered.set()
            await finish.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})
        guarded = beta.BetaMiddleware(endpoint, owner=app)
        first = asyncio.create_task(asgi_request(guarded, "GET", "/theorems/applicable", host="192.0.2.1"))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            status, body, headers = await asgi_request(guarded, "GET", "/theorems/applicable", host="192.0.2.2")
            assert status == 429 and body["code"] == "beta.busy"
            assert headers[b"retry-after"] == b"2"
            # A normal read from a third client remains available.
            assert (await asgi_request(beta.BetaMiddleware(
                lambda scope, receive, send: successful(scope, receive, send), owner=app),
                "GET", "/health", host="192.0.2.3"))[0] == 200
        finally:
            finish.set()
            await first
        assert beta_runtime.active_heavy == 0
        assert (await asgi_request(guarded, "GET", "/theorems/applicable", host="192.0.2.2"))[0] == 200
        assert beta_runtime.active_heavy == 0
    asyncio.run(run())


async def successful(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


@pytest.mark.parametrize("ending", ["exception", "length", "chunks", "disconnect"])
def test_heavy_slot_released_on_all_exit_paths(beta_runtime, ending):
    async def run():
        async def endpoint(scope, receive, send):
            raise RuntimeError("injected endpoint failure")
        guarded = beta.BetaMiddleware(endpoint, owner=app)
        if ending == "exception":
            with pytest.raises(RuntimeError):
                await asgi_request(guarded, "GET", "/theorems/applicable")
        elif ending == "disconnect":
            scope = {"type": "http", "method": "GET", "path": "/theorems/applicable", "root_path": "",
                     "headers": [], "client": ("192.0.2.1", 80)}
            async def receive():
                return {"type": "http.disconnect"}
            async def send(message):
                pytest.fail("disconnected request must not send")
            await guarded(scope, receive, send)
        else:
            maximum = beta.Limits().body_bytes
            kwargs = ({"headers": [(b"content-length", str(maximum + 1).encode())]} if ending == "length"
                      else {"chunks": [b"x" * maximum, b"x"]})
            assert (await asgi_request(guarded, "GET", "/theorems/applicable", **kwargs))[0] == 413
        assert beta_runtime.active_heavy == 0
        assert (await asgi_request(beta.BetaMiddleware(successful, owner=app),
                                  "GET", "/theorems/applicable", host="192.0.2.2"))[0] == 200
        assert beta_runtime.active_heavy == 0
    asyncio.run(run())


@pytest.mark.parametrize("enabled", [False, True])
def test_export_disabled_only_in_beta(live_api, beta_runtime, monkeypatch, enabled):
    if not enabled:
        monkeypatch.delenv("DEM_BETA")
    async def application(scope, receive, send):
        async def forward(message):
            if not enabled and message["type"] == "http.response.body":
                message = {**message, "body": b""}
            await send(message)
        await app(scope, receive, forward)
    status, body, headers = asyncio.run(asgi_request(application, "GET", "/workspace/export"))
    if enabled:
        assert status == 403 and body["code"] == "beta.disabled"
    else:
        assert status == 200 and headers[b"content-type"] == b"application/vnd.dem.workspace+zip"


def test_heavy_limit_is_advertised(live_api, beta_runtime, monkeypatch):
    context = beta.Limits()
    assert context.heavy_concurrent == 1
    # Config's direct lookup follows the same test-owned API as its dependency.
    from webapi import deps
    from uuid import UUID
    monkeypatch.setattr(deps, "get_workspace_request_context", lambda *args: deps.WorkspaceRequestContext(
        UUID(int=0), "test", None, "local.workspace", live_api))
    status, body, _ = asyncio.run(asgi_request(app, "GET", "/config"))
    assert status == 200 and body["beta"]["limits"]["heavy_concurrent"] == 1
