from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import event, func, select, text

from dem.api import DemServices
from dem.db.models.language import Formula, FormulaType, Symbol, SymbolAlias
from dem.db.models.tag import Tag
from dem.db.models.theorem import ProofStep, Theorem
from dem.types import AssumptionStepInput, SymbolTypeName, Token
from webapi import beta, deps
from webapi.main import app
from beta_http import asgi_request

from beta_fixture import base_phase
SEED_PHASE = base_phase()


@pytest.fixture
def boundary(fresh_seeded_session, monkeypatch):
    session = fresh_seeded_session
    monkeypatch.setenv("DEM_BETA", "1")
    monkeypatch.delenv("DEM_READ_ONLY", raising=False)
    monkeypatch.delenv("DEM_BETA_FLAG_DIR", raising=False)
    monkeypatch.delenv("DEM_BETA_STATUS_FILE", raising=False)
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    monkeypatch.setattr(app.state, "beta_limits", beta.Limits(), raising=False)
    bind = session.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind

    @contextmanager
    def transaction():
        # Same transactional seam as DemApi; use savepoints only to preserve
        # the test fixture's outer transaction on PostgreSQL.
        with session.begin_nested():
            yield DemServices(session)

    context = deps.WorkspaceRequestContext(UUID(int=0), "test", None,
                                           "local.workspace", SimpleNamespace(engine=engine, transaction=transaction))
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[deps.get_workspace_request_context] = lambda: context
    monkeypatch.setattr(deps, "get_workspace_request_context", lambda *args: context)

    def request(method, path, body=None, **kwargs):
        return asyncio.run(asgi_request(app, method, path, body, **kwargs))

    def limits(**changes):
        app.state.beta_limits = replace(beta.Limits(), **changes)

    try:
        yield session, DemServices(session), request, limits, engine
    finally:
        session.info.pop(beta.SESSION_KEY, None)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def proposition(dem):
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    symbol = dem.symbols.register("betaP", kind.id, 0)
    return dem.formulas.register([Token(symbol_id=symbol.id)]), symbol


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", " yes "])
def test_enabled_values(monkeypatch, value):
    monkeypatch.setenv("DEM_BETA", value)
    assert beta.enabled()


def test_disabled_is_transparent(boundary, monkeypatch, tmp_path):
    session, dem, request, limits, _ = boundary
    limits(name=1, body_bytes=1, read_burst=1, write_per_minute=1)
    monkeypatch.delenv("DEM_BETA")
    monkeypatch.setenv("DEM_BETA_FLAG_DIR", str(tmp_path))
    (tmp_path / "read_only").touch()
    assert request("GET", "/config")[:2] == (200, {"read_only": False})
    for name in ["long-one", "long-two"]:
        assert request("POST", "/tags", {"name": name})[0] == 201
    assert request("GET", "/openapi.json")[0] == 200


@pytest.mark.parametrize("field,limit_name", [("name", "name"), ("remarks", "description"), ("latex_template", "notation")])
def test_text_limits_exact_and_over_with_rollback(boundary, field, limit_name):
    session, dem, request, limits, _ = boundary
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    limits(**{limit_name: 4})
    body = {"name": "one", "symbol_type_id": kind.id, "arity": 0, field: "a" * 4}
    assert request("POST", "/symbols", body)[0] == 201
    before = session.scalar(select(func.count()).select_from(Symbol))
    body.update(name="two")
    body[field] = "b" * 5
    status, result, _ = request("POST", "/symbols", body)
    assert status == 422 and result["code"] == "beta.limit_exceeded"
    assert result["limit"] == field
    assert session.scalar(select(func.count()).select_from(Symbol)) == before


@pytest.mark.parametrize("entity", ["axioms", "definitions", "theorems", "axiom-systems", "tags", "aliases", "proofs", "explorations"])
def test_all_authored_names_share_the_guard(boundary, entity):
    session, dem, request, limits, _ = boundary
    formula, symbol = proposition(dem)
    theorem = dem.theorems.register("betaBase", formula.id, [])
    limits(name=8)
    body = {"name": "x" * 9}
    path = f"/{entity}"
    if entity == "axioms":
        body["formula_id"] = formula.id
    elif entity == "definitions":
        body.update(kind="logical", param_symbol_ids=[symbol.id], body_formula_id=formula.id)
    elif entity == "theorems":
        body.update(conclusion_formula_id=formula.id, premise_formula_ids=[])
    elif entity == "aliases":
        path, body = f"/symbols/{symbol.id}/aliases", {"alias": "x" * 9}
    elif entity == "proofs":
        body["theorem_id"] = theorem.id
    elif entity == "explorations":
        body["premise_formula_ids"] = [formula.id]
    counts = {table.name: session.scalar(select(func.count()).select_from(table))
              for table in [Symbol.__table__, Theorem.__table__, Tag.__table__]}
    status, result, _ = request("POST", path, body)
    assert status == 422 and result["code"] == "beta.limit_exceeded", result
    for table in [Symbol.__table__, Theorem.__table__, Tag.__table__]:
        assert session.scalar(select(func.count()).select_from(table)) == counts[table.name]


def test_description_update_and_alias_boundaries(boundary):
    session, dem, request, limits, _ = boundary
    formula, symbol = proposition(dem)
    axiom = dem.axioms.register("betaAxiom", formula.id)
    limits(description=4, name=4)
    assert request("PATCH", f"/axioms/{axiom.id}/description", {"description": "a" * 4})[0] == 200
    assert request("PATCH", f"/axioms/{axiom.id}/description", {"description": "b" * 5})[0] == 422
    session.refresh(axiom)
    assert axiom.description == "aaaa"
    assert request("POST", f"/symbols/{symbol.id}/aliases", {"alias": "AAAA"})[0] == 201
    assert request("POST", f"/symbols/{symbol.id}/aliases", {"alias": "BBBBB"})[0] == 422
    assert session.scalar(select(SymbolAlias.id).where(SymbolAlias.alias == "BBBBB")) is None


def test_formula_limit_including_indirect_generation(boundary):
    session, dem, request, limits, _ = boundary
    formula, symbol = proposition(dem)
    negation = dem.symbols.get_by_role("implication")
    # Binary logical core; no foundation-specific symbols are assumed.
    tokens = [{"symbol_id": negation.id}, {"symbol_id": symbol.id}, {"symbol_id": symbol.id}]
    limits(formula_tokens=3)
    assert request("POST", "/formulas", {"tokens": tokens})[0] == 201
    limits(formula_tokens=2)
    # A second independently named variable avoids returning an interned formula.
    other = dem.symbols.register("betaQ", symbol.symbol_type_id, 0)
    tokens[-1] = {"symbol_id": other.id}
    before = session.scalar(select(func.count()).select_from(Formula))
    result = request("POST", "/formulas", {"tokens": tokens})
    assert result[0] == 422 and result[1]["limit"] == "formula_tokens"
    assert session.scalar(select(func.count()).select_from(Formula)) == before
    theorem = dem.theorems.register("betaIndirect", formula.id, [])
    proof = dem.proofs.create_proof(theorem.id)
    dem.proofs.add_step(proof.id, AssumptionStepInput(), formula.id)
    before = session.scalar(select(func.count()).select_from(Formula))
    # P -> P is already interned above, use Q -> Q for a newly derived formula.
    q = dem.formulas.register([Token(symbol_id=other.id)])
    dem.proofs.add_step(proof.id, AssumptionStepInput(), q.id)
    result = request("POST", f"/proofs/{proof.id}/steps", {"kind": "imp_intro", "assumption_step_ord": 1, "body_step_ord": 1})
    assert result[0] == 422 and result[1]["limit"] == "formula_tokens", result
    assert len(dem.proofs.list_steps(proof.id)) == 2
    assert session.scalar(select(func.count()).select_from(Formula)) == before + 1


def test_premise_and_step_limits_exact_and_over(boundary):
    session, dem, request, limits, _ = boundary
    formula, _ = proposition(dem)
    limits(theorem_premises=2, proof_steps=2)
    body = {"name": "betaPremises", "conclusion_formula_id": formula.id, "premise_formula_ids": [formula.id] * 2}
    assert request("POST", "/theorems", body)[0] == 201
    before = session.scalar(select(func.count()).select_from(Theorem))
    body.update(name="betaTooMany", premise_formula_ids=[formula.id] * 3)
    result = request("POST", "/theorems", body)
    assert result[0] == 422 and result[1]["limit"] == "theorem_premises"
    assert session.scalar(select(func.count()).select_from(Theorem)) == before
    theorem = dem.theorems.get_by_name("betaPremises", namespace="local.workspace")
    proof = dem.proofs.create_proof(theorem.id)
    step = {"kind": "premise", "premise_ord": 0}
    assert request("POST", f"/proofs/{proof.id}/steps", step)[0] == 201
    assert request("POST", f"/proofs/{proof.id}/steps", step)[0] == 201
    result = request("POST", f"/proofs/{proof.id}/steps", step)
    assert result[0] == 422 and result[1]["limit"] == "proof_steps"
    assert len(dem.proofs.list_steps(proof.id)) == 2


@pytest.mark.parametrize("method,path,kind,heavy", [
    ("POST", "/formulas/parse", "read", False), ("POST", "/formulas/print", "read", False),
    ("POST", "/proofs/{id}/steps/suggest", "write", True),
    ("POST", "/proofs/{id}/steps/suggest-backward", "write", True),
    ("GET", "/theorems/applicable", "read", True), ("POST", "/proofs/{id}/validate", "write", True),
    ("POST", "/formulas/search", "write", True), ("POST", "/formulas/validate", "write", True),
    ("POST", "/proofs/compute-gen-tokens", "write", True),
    ("POST", "/proofs/compute-substituted-tokens", "write", True),
    ("GET", "/workspace/export", "read", True), ("PATCH", "/symbols/{id}/notation", "write", False),
])
def test_route_categories(method, path, kind, heavy):
    assert beta.category(method, path) == kind
    assert (path in beta.HEAVY_ROUTES) == heavy


def test_buckets_refill_ipv6_and_lru():
    now = [0.0]
    runtime = beta.Runtime(lambda: now[0])
    limits = replace(beta.Limits(), read_burst=1, read_per_minute=60, max_clients=2)
    key = runtime.enter("2001:db8::1", "read", "/health", limits)
    runtime.leave(key)
    with pytest.raises(beta.BetaReject) as rejected:
        runtime.enter("2001:db8::2", "read", "/health", limits)
    assert rejected.value.retry == 1
    now[0] += 1
    key = runtime.enter("2001:db8::2", "read", "/health", limits)
    runtime.leave(key)
    for host in ["1.1.1.1", "2.2.2.2"]:
        key = runtime.enter(host, "read", "/health", limits)
        runtime.leave(key)
    assert len(runtime.clients) == 2 and "2001:db8::/64" not in runtime.clients
    assert beta.source_key("::ffff:1.2.3.4") == "1.2.3.4"


@pytest.mark.parametrize("field,kind,route", [
    ("read_burst", "read", "/health"), ("write_per_minute", "write", "/tags"),
    ("write_per_hour", "write", "/tags"), ("global_write_per_hour", "write", "/tags"),
    ("heavy_per_minute", "read", "/theorems/applicable"),
    ("export_per_ten_minutes", "read", "/workspace/export"),
])
def test_each_bucket(field, kind, route):
    runtime = beta.Runtime(lambda: 0)
    limits = replace(beta.Limits(), **{field: 1})
    key = runtime.enter("1.2.3.4", kind, route, limits)
    runtime.leave(key)
    host = "5.6.7.8" if field == "global_write_per_hour" else "1.2.3.4"
    with pytest.raises(beta.BetaReject) as exc:
        runtime.enter(host, kind, route, limits)
    assert exc.value.code == "beta.rate_limited" and exc.value.retry > 0


def test_concurrent_and_active_client_eviction():
    runtime = beta.Runtime()
    limits = replace(beta.Limits(), concurrent=1, max_clients=1)
    key = runtime.enter("1.2.3.4", "read", "/health", limits)
    for host in ["1.2.3.4", "5.6.7.8"]:
        with pytest.raises(beta.BetaReject):
            runtime.enter(host, "read", "/health", limits)
    runtime.leave(key)
    assert runtime.enter("5.6.7.8", "read", "/health", limits)


def test_http_concurrent_limit_and_release(boundary):
    async def run():
        entered = 0
        all_entered, release = asyncio.Event(), asyncio.Event()
        async def endpoint(scope, receive, send):
            nonlocal entered
            entered += 1
            if entered == 4:
                all_entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})
        application = beta.BetaMiddleware(endpoint, owner=app)
        pending = [asyncio.create_task(asgi_request(application, "GET", "/theorems")) for _ in range(8)]
        try:
            await asyncio.wait_for(all_entered.wait(), 5)
            for _ in range(100):
                if beta.runtime.waiting == 4:
                    break
                await asyncio.sleep(.001)
            assert entered == 4 and beta.runtime.waiting == 4
            assert not any(task.done() for task in pending)
        finally:
            release.set()
            results = await asyncio.gather(*pending)
        assert len(results) == 8 and all(result[0] == 200 for result in results)
        assert beta.runtime.waiting == 0
        assert all(client.active == 0 and not client.waiters for client in beta.runtime.clients.values())
        assert (await asgi_request(application, "GET", "/health"))[0] == 200
    asyncio.run(run())


def test_http_concurrent_wait_timeout(boundary):
    _, _, _, configure, _ = boundary
    configure(concurrent=1, concurrent_wait_seconds=.03)
    admission = beta.runtime.enter("127.0.0.1", "read", "/health", app.state.beta_limits)
    try:
        status, body, headers = asyncio.run(asgi_request(app, "GET", "/health"))
        assert status == 429 and body["code"] == "beta.rate_limited"
        assert body["detail"] == "Too many concurrent requests"
        assert int(headers[b"retry-after"]) >= 1
        assert beta.runtime.waiting == 0
        # Timeout does not spend a token or leak a slot.
        client = beta.runtime.clients["127.0.0.1"]
        assert client.active == 1 and not client.waiters
        assert client.buckets["read"][0] == 299
    finally:
        beta.runtime.leave(admission)


@pytest.mark.parametrize("bound", ["source_waiters", "global_waiters"])
def test_concurrent_waiter_bound_and_cancellation(bound):
    async def run():
        runtime = beta.Runtime()
        limits = replace(beta.Limits(), concurrent=1, max_clients=2,
                         **{bound: 1}, concurrent_wait_seconds=.2)
        active = runtime.enter("one", "read", "/health", limits)
        second = runtime.enter("two", "read", "/health", limits)
        waiting = asyncio.create_task(runtime.enter_async("one", "read", "/health", limits))
        try:
            for _ in range(100):
                if runtime.waiting == 1:
                    break
                await asyncio.sleep(.001)
            assert runtime.waiting == 1
            with pytest.raises(beta.BetaReject) as rejected:
                await runtime.enter_async("one" if bound == "source_waiters" else "two", "read", "/health", limits)
            assert rejected.value.detail == "Concurrency wait queue is full"
            assert rejected.value.code == "beta.rate_limited"
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            assert runtime.waiting == 0 and not runtime.clients["one"].waiters
            # Cancelled waiters free queue capacity for a subsequent request.
            waiting = asyncio.create_task(runtime.enter_async("one", "read", "/health", limits))
            await asyncio.sleep(.01)
            runtime.leave(active)
            active = await asyncio.wait_for(waiting, 1)
        finally:
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
            runtime.leave(active)
            runtime.leave(second)
        assert runtime.waiting == 0
    asyncio.run(run())


def test_read_budget_defaults_and_refill():
    now = [0.0]
    runtime = beta.Runtime(lambda: now[0])
    limits = beta.Limits()
    assert (limits.read_per_minute, limits.read_burst) == (600, 300)
    for _ in range(300):
        runtime.leave(runtime.enter("one", "read", "/health", limits))
    with pytest.raises(beta.BetaReject):
        runtime.enter("one", "read", "/health", limits)
    now[0] += .1
    runtime.leave(runtime.enter("one", "read", "/health", limits))


def test_forwarded_for_is_ignored_and_heavy_also_spends_read(boundary):
    _, _, request, limits, _ = boundary
    limits(read_burst=1)
    assert request("GET", "/health", headers=[(b"x-forwarded-for", b"1.1.1.1")])[0] == 200
    assert request("GET", "/health", headers=[(b"x-forwarded-for", b"2.2.2.2")])[0] == 429
    runtime = beta.Runtime(lambda: 0)
    settings = replace(beta.Limits(), read_burst=1)
    key = runtime.enter("test", "read", "/theorems/applicable", settings)
    runtime.leave(key)
    with pytest.raises(beta.BetaReject):
        runtime.enter("test", "read", "/health", settings)


@pytest.mark.parametrize("after_upgrade", [False, True], ids=["direct", "after-upgrade"])
def test_actual_rate_route_matching_retry_and_logs(boundary, caplog, tmp_path, monkeypatch, after_upgrade):
    if after_upgrade:
        import logging
        from pathlib import Path
        from alembic import command
        from alembic.config import Config

        repository = Path(__file__).resolve().parents[1]
        config = Config(str(repository / "alembic.ini"))
        config.set_main_option("script_location", str(repository / "alembic"))
        monkeypatch.setenv("DEM_DATABASE_URL", "sqlite+pysqlite:///" + (tmp_path / "migration.db").as_posix())
        monkeypatch.setattr(beta.log, "disabled", False)
        root = logging.getLogger()
        capture_handlers = root.handlers[:]
        try:
            command.upgrade(config, "head")
        finally:
            # fileConfig replaces root handlers. Restore pytest's capture sinks,
            # without changing the application's logger state after migration.
            root.handlers[:] = capture_handlers
        assert beta.log.disabled is False
    _, _, request, limits, _ = boundary
    limits(write_per_minute=1)
    assert request("POST", "/proofs/12345/steps/suggest", {})[0] == 422
    status, body, headers = request("POST", "/proofs/67890/steps/suggest", {})
    assert status == 429 and body["code"] == "beta.rate_limited"
    assert int(headers[b"retry-after"]) > 0
    assert "route=/proofs/{id}/steps/suggest" in caplog.text
    assert "127.0.0.1" not in caplog.text


@pytest.mark.parametrize("chunked", [False, True])
def test_body_limit_exact_and_over(boundary, chunked, caplog):
    _, _, request, limits, _ = boundary
    limits(body_bytes=4)
    kwargs = {"chunks": [b"ab", b"cd"]} if chunked else {"chunks": [b"abcd"], "headers": [(b"content-length", b"4")]}
    assert request("GET", "/health", **kwargs)[0] == 200
    kwargs = {"chunks": [b"ab", b"cde"]} if chunked else {"headers": [(b"content-length", b"5")]}
    status, body, _ = request("GET", "/health", **kwargs)
    assert status == 413 and body["code"] == "beta.body_too_large"
    assert "beta.body_too_large" in caplog.text


def test_maintenance_read_only_priority_and_live_flag(boundary, tmp_path, monkeypatch, caplog):
    _, _, request, _, _ = boundary
    monkeypatch.setenv("DEM_BETA_FLAG_DIR", str(tmp_path))
    flag = tmp_path / "read_only"
    flag.touch()
    assert request("GET", "/tags")[0] == 200
    result = request("POST", "/tags", {"name": "betaTag"})
    assert result[0] == 503 and result[1]["code"] == "beta.maintenance"
    assert "beta.maintenance" in caplog.text
    monkeypatch.setenv("DEM_READ_ONLY", "1")
    assert request("POST", "/tags", {"name": "betaTag"})[:2] == (403, {"detail": "read-only mode: write operations are disabled"})
    monkeypatch.delenv("DEM_READ_ONLY")
    flag.unlink()
    assert request("POST", "/tags", {"name": "betaTag"})[0] == 201


@pytest.mark.parametrize("field,model", [("formulas", Formula), ("theorems", Theorem), ("steps", ProofStep), ("database_bytes", None)])
def test_capacity_limits_cache_and_force(boundary, field, model):
    session, _, request, limits, engine = boundary
    maximum = session.scalar(select(func.count()).select_from(model)) if model else 1
    limits(**{field: maximum})
    assert beta.runtime.is_full(engine, app.state.beta_limits, force=True)
    result = request("POST", "/tags", {"name": "betaNoSpace"})
    assert result[0] == 503 and result[1]["code"] == "beta.full"
    assert request("GET", "/tags")[0] == 200
    assert session.scalar(select(Tag.id).where(Tag.name == "betaNoSpace")) is None
    limits()
    assert not beta.runtime.is_full(engine, app.state.beta_limits, force=True)
    with event_counter(engine) as queries:
        assert not beta.runtime.is_full(engine, app.state.beta_limits)
    assert not queries


def test_capacity_expires_after_sixty_seconds(boundary):
    _, _, _, _, engine = boundary
    clock = [0]
    runtime = beta.Runtime(lambda: clock[0])
    assert not runtime.is_full(engine, beta.Limits())
    clock[0] = 59
    with event_counter(engine) as queries:
        runtime.is_full(engine, beta.Limits())
    assert not queries
    clock[0] = 60
    with event_counter(engine) as queries:
        runtime.is_full(engine, beta.Limits())
    assert queries


@contextmanager
def event_counter(engine):
    queries = []
    def before(*args):
        queries.append(args[2])
    event.listen(engine, "before_cursor_execute", before)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", before)


def test_config_docs_roles_and_reset_status(boundary, tmp_path, monkeypatch):
    _, _, request, _, _ = boundary
    for path in ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]:
        assert request("GET", path)[0] == 404
    result = request("POST", "/symbol-roles", {})
    assert result[0] == 403 and result[1]["code"] == "beta.disabled"
    status_file = tmp_path / "status.json"
    monkeypatch.setenv("DEM_BETA_STATUS_FILE", str(status_file))
    for content in [None, "bad", "[]", '{"last_reset_at":"bad"}']:
        if content is not None:
            status_file.write_text(content)
        result = request("GET", "/config")
        assert result[0] == 200
        assert result[1]["beta"]["last_reset_at"] is None
    status_file.write_text('{"last_reset_at":"2026-10-21T00:00:00Z","next_reset_at":"2026-10-28T00:00:00Z"}')
    result = request("GET", "/config")[1]
    assert result["read_only"] is False and result["beta"]["enabled"]
    assert result["beta"]["write_state"] == "open"
    assert result["beta"]["last_reset_at"] == "2026-10-21T00:00:00Z"
    assert result["beta"]["limits"]["formula_tokens"] == 2000


def test_ready_checks_database(boundary, monkeypatch):
    _, _, request, _, engine = boundary
    with event_counter(engine) as queries:
        assert request("GET", "/health/ready")[:2] == (200, {"status": "ok"})
    assert "SELECT 1" in queries
    monkeypatch.setattr(engine, "connect", lambda: (_ for _ in ()).throw(RuntimeError("private connection data")))
    assert request("GET", "/health/ready")[:2] == (503, {"status": "unavailable"})
    assert request("GET", "/health")[:2] == (200, {"status": "ok"})


@pytest.mark.parametrize("guard", ["tier_a", "tier_b", "published", "unique", "unknown_check", "unknown_message"])
@pytest.mark.parametrize("beta_enabled", [False, True])
def test_real_db_guard_mapping(boundary, guard, beta_enabled, monkeypatch):
    from fastapi import FastAPI
    from webapi.errors import register_exception_handlers
    from dem.db.models.package import Package, PackageRelease
    from datetime import datetime, timezone

    session, dem, request, _, _ = boundary
    if not beta_enabled:
        monkeypatch.delenv("DEM_BETA")
    formula, symbol = proposition(dem)
    theorem = dem.theorems.register("betaGuardTheorem", formula.id, [])
    if guard == "published":
        package = Package(name="beta-guard-package", owner="test")
        session.add(package)
        session.flush()
        release = PackageRelease(package_id=package.id, version="1.0.0", dem_runtime_range="*", manifest={})
        session.add(release)
        session.flush()
        symbol.release_id = release.id
        session.flush()
        release.published_at = datetime.now(timezone.utc)
        session.flush()
        status, body, _ = request("PATCH", f"/symbols/{symbol.id}/latex-template", {"latex_template": "changed"})
        assert status == 409 and body["code"] == "db.guard_rejected"
    application = FastAPI()
    register_exception_handlers(application)

    @application.post("/fire")
    def fire():
        with session.begin_nested():
            if guard == "tier_a":
                session.execute(text("UPDATE theorem SET status='proven' WHERE id=:id"), {"id": theorem.id})
            elif guard == "tier_b":
                session.execute(text("UPDATE formula SET hash='changed' WHERE id=:id"), {"id": formula.id})
            elif guard == "published":
                session.execute(text("UPDATE symbol SET remarks='changed' WHERE id=:id"), {"id": symbol.id})
            elif guard == "unique":
                session.execute(text("INSERT INTO tag(name) VALUES ('betaUnique')"))
                session.execute(text("INSERT INTO tag(name) VALUES ('betaUnique')"))
            elif guard == "unknown_check":
                session.execute(text("UPDATE theorem SET status='bad' WHERE id=:id"), {"id": theorem.id})
            else:
                if session.get_bind().dialect.name == "sqlite":
                    session.execute(text("CREATE TEMP TRIGGER beta_unknown BEFORE INSERT ON tag BEGIN SELECT RAISE(ABORT, 'unknown guard'); END"))
                else:
                    session.execute(text("CREATE FUNCTION pg_temp.beta_unknown() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'unknown guard' USING ERRCODE='23514'; END $$"))
                    session.execute(text("CREATE TRIGGER beta_unknown BEFORE INSERT ON tag FOR EACH ROW EXECUTE FUNCTION pg_temp.beta_unknown()"))
                session.execute(text("INSERT INTO tag(name) VALUES ('betaUnknown')"))
        return {"ok": True}

    status, body, _ = asyncio.run(asgi_request(application, "POST", "/fire", raise_app_exceptions=False))
    if guard in {"tier_a", "tier_b", "published"}:
        assert status == 409 and body["code"] == "db.guard_rejected", body
        assert set(body) == {"detail", "code"}
    else:
        assert status == 500 and body == "Internal Server Error"
    session.expire_all()
    assert session.get(Theorem, theorem.id).status == "conjecture"
    assert session.get(Symbol, symbol.id).remarks != "changed"


@pytest.mark.parametrize("spelling", ["0{}", "+{}", "{}.0"])
def test_two_threads_editing_same_draft(boundary, seed_snapshot_factory, spelling):
    """Hold a real INSERT in flight, then submit the conflicting API request."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    session, dem, request, _, engine = boundary
    # Use seed formulas so only mutable draft data must be cleaned up. All
    # concurrent requests get independent sessions and database connections.
    formula = session.scalars(select(Formula).where(Formula.formula_type_id.in_(
        select(FormulaType.id).where(FormulaType.code == 'proposition')))).first()
    independent_engine = None
    if engine.dialect.name == "postgresql":
        from sqlalchemy import create_engine
        factory = seed_snapshot_factory.postgresql
        database = factory._worker_database("beta1_race", factory.get(base_phase()))
        independent_engine = create_engine(engine.url.set(database=database))
        engine = independent_engine
    from dem.api import DemApi
    from uuid import uuid4
    api = DemApi(engine)
    with api.transaction() as setup:
        theorem = setup.theorems.register(f"betaConcurrent-{uuid4().hex}", formula.id, [formula.id])
        proof = setup.proofs.create_proof(theorem.id)
        proof_id = proof.id
    previous = app.dependency_overrides.copy()
    context = deps.WorkspaceRequestContext(UUID(int=0), "test", None, "local.workspace", api)
    # boundary monkeypatches the function for config; replace the original
    # dependency key already in the map instead of a newly patched callable.
    for key in list(app.dependency_overrides):
        if getattr(key, '__name__', '') == 'get_workspace_request_context':
            app.dependency_overrides[key] = lambda: context
    inserted, resume = Event(), Event()
    def pause(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO PROOF_STEP "):
            inserted.set()
            assert resume.wait(10), "second request did not release first"
    event.listen(engine, "before_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(request, "POST", f"/proofs/{proof_id}/steps", {"kind": "premise", "premise_ord": 0})
            assert inserted.wait(10), "first request did not reach INSERT"
            second = pool.submit(request, "POST", f"/proofs/{spelling.format(proof_id)}/steps", {"kind": "premise", "premise_ord": 0})
            result = second.result(timeout=10)
            resume.set()
            assert result[0] == 409, result
            assert first.result(timeout=10)[0] == 201
        with api.transaction() as check:
            assert len(check.proofs.list_steps(proof_id)) == 1
            # Real kernel validation, with no mocks.
            check.proofs.validate(proof_id)
            assert check.proofs.get(proof_id).status == "verified"
    finally:
        resume.set()
        event.remove(engine, "before_cursor_execute", pause)
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if independent_engine is not None:
            independent_engine.dispose()
        # This database clone is dropped by the fixture factory. Verified data
        # cannot and must not be removed by bypassing its immutability guards.
