"""Commit/recursion failures must roll back before an HTTP response is sent."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from dem.api import DemApi
from dem.db.models.language import Formula, FormulaToken, FormulaType
from dem.db.models.tag import Tag
from dem.db.models.theorem import ProofStep
from dem.identity import DEFAULT_NAMESPACE_NAME
from dem.services.formula import compute_hash
from dem.types import SymbolTypeName, Token
from webapi import beta, deps
from webapi.main import app
from beta_http import asgi_request

SEED_PHASE = "public_core"


@pytest.fixture
def live_api(fresh_seeded_session, seed_snapshot_factory, monkeypatch):
    """Real top-level transactions, including PostgreSQL deferred COMMIT guards."""
    bind = fresh_seeded_session.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    own_engine = None
    if engine.dialect.name == "postgresql":
        factory = seed_snapshot_factory.postgresql
        name = factory._worker_database("beta1_fix", factory.get("public_core"))
        own_engine = create_engine(engine.url.set(database=name))
        engine = own_engine
    api = DemApi(engine)
    context = deps.WorkspaceRequestContext(UUID(int=0), "test", None, "local.workspace", api)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[deps.get_workspace_request_context] = lambda: context
    monkeypatch.delenv("DEM_READ_ONLY", raising=False)
    monkeypatch.delenv("DEM_BETA", raising=False)
    monkeypatch.delenv("DEM_BETA_FLAG_DIR", raising=False)
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    monkeypatch.setattr(app.state, "beta_limits", beta.Limits(), raising=False)
    try:
        yield api
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if own_engine is not None:
            own_engine.dispose()


def request(method, path, body=None, **kwargs):
    return asyncio.run(asgi_request(app, method, path, body, **kwargs))


def row_counts(api):
    with api.engine.connect() as connection:
        return tuple(connection.scalar(select(func.count()).select_from(model))
                     for model in (Tag, Formula, FormulaToken, ProofStep))


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError, RecursionError])
def test_commit_failure_is_not_success_and_rolls_back(live_api, monkeypatch, enabled, failure):
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    class FailingSession(Session):
        pass
    reached = []
    @event.listens_for(FailingSession, "before_commit")
    def fail_commit(session):
        reached.append(True)
        raise failure("private diagnostic must not appear in the response")
    live_api.session_factory = sessionmaker(live_api.engine, class_=FailingSession)
    before = row_counts(live_api)
    status, body, _ = request("POST", "/tags", {"name": f"commit-{uuid4().hex}"}, raise_app_exceptions=False)
    assert reached == [True]
    if failure is RecursionError:
        assert status == 422 and body["code"] == "formula.too_deep", (status, body)
        assert "private diagnostic" not in str(body)
    else:
        assert status == 500 and body == "Internal Server Error", (status, body)
    assert row_counts(live_api) == before


@pytest.mark.parametrize("enabled", [False, True])
def test_postgresql_deferred_guard_rejects_before_send(live_api, monkeypatch, enabled):
    if live_api.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL has the real deferred well-formedness guard")
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    class IncompleteFormulaSession(Session):
        pass
    inserted = []
    @event.listens_for(IncompleteFormulaSession, "before_commit")
    def insert_incomplete_formula(session):
        kind = session.scalar(select(FormulaType.id).where(FormulaType.code == "proposition"))
        # Core SQL deliberately constructs an incomplete formula. INSERT succeeds;
        # the actual PostgreSQL constraint trigger rejects only at outer COMMIT.
        session.execute(insert(Formula).values(public_id=uuid4().hex, hash=uuid4().hex,
                                               formula_type_id=kind, token_count=1))
        inserted.append(True)
    live_api.session_factory = sessionmaker(live_api.engine, class_=IncompleteFormulaSession)
    before = row_counts(live_api)
    status, body, _ = request("POST", "/tags", {"name": f"deferred-{uuid4().hex}"}, raise_app_exceptions=False)
    assert inserted == [True]
    assert status == 409 and body["code"] == "db.guard_rejected", (status, body)
    assert set(body) == {"detail", "code"}
    assert row_counts(live_api) == before


def test_all_service_dependencies_finish_in_function_scope():
    root = Path(__file__).resolve().parents[1] / "webapi"
    counts = {"dem_services": 0, "get_local_namespace_name": 0}
    for path in [root / "deps.py", *sorted((root / "routers").glob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "Depends" or not node.args:
                continue
            argument = node.args[0]
            if not isinstance(argument, ast.Name) or argument.id not in counts:
                continue
            counts[argument.id] += 1
            scopes = [keyword.value for keyword in node.keywords if keyword.arg == "scope"]
            assert len(scopes) == 1 and ast.literal_eval(scopes[0]) == "function", (path.name, node.lineno)
    assert counts == {"dem_services": 92, "get_local_namespace_name": 7}


def test_namespace_and_service_dependencies_share_one_transaction(live_api):
    class TrackedSession(Session):
        pass
    events = []
    @event.listens_for(TrackedSession, "after_transaction_create")
    def started(session, transaction):
        if transaction.parent is None:
            events.append("begin")
    @event.listens_for(TrackedSession, "after_commit")
    def committed(session):
        events.append("commit")
    with live_api.session() as dem:
        kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id
    live_api.session_factory = sessionmaker(live_api.engine, class_=TrackedSession, expire_on_commit=False)
    name = f"singleTransaction{uuid4().hex}"
    status, body, _ = request("POST", "/symbols", {"name": name, "symbol_type_id": kind, "arity": 0})
    assert status == 201 and body["name"] == name
    assert body["namespace_name"] == "local.workspace"
    assert events == ["begin", "commit"]


def test_beta_database_defaults_are_reduced():
    limits = beta.Limits()
    assert (limits.formulas, limits.theorems, limits.steps) == (20_000, 2000, 40_000)
    assert limits.database_bytes == 1024 ** 3


def test_export_closes_its_direct_session_before_sending(live_api):
    events = []
    @event.listens_for(live_api.engine, "checkin")
    def checkin(*args):
        events.append("closed")
    async def observe(scope, receive, send):
        async def observed_send(message):
            if message["type"] == "http.response.start":
                assert events and events[-1] == "closed"
                events.append("response")
            # Keep the assertion about resource ordering independent of archive
            # decoding. Existing export tests verify the binary archive itself.
            if message["type"] == "http.response.body":
                message = {**message, "body": b""}
            await send(message)
        await app(scope, receive, observed_send)
    try:
        assert asyncio.run(asgi_request(observe, "GET", "/workspace/export"))[0] == 200
        assert "response" in events
    finally:
        event.remove(live_api.engine, "checkin", checkin)


class DeepInputs:
    def __init__(self, api):
        self.api = api
        with api.transaction() as dem:
            kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
            suffix = uuid4().hex
            self.p = dem.symbols.register(f"deepP{suffix}", kind.id, 0).id
            self.q = dem.symbols.register(f"deepQ{suffix}", kind.id, 0).id
            self.r = dem.symbols.register(f"deepR{suffix}", kind.id, 0).id
            self.neg = dem.symbols.get_by_name("¬", namespace=DEFAULT_NAMESPACE_NAME).id
            self.imp = dem.symbols.get_by_role("implication").id
            base = dem.formulas.register([Token(symbol_id=self.q)])
            self.axioms = {}
            for shape, tokens in [("unary", [Token(symbol_id=self.neg), Token(symbol_id=self.p)]),
                                  ("right", [Token(symbol_id=self.imp), Token(symbol_id=self.q), Token(symbol_id=self.p)])]:
                formula = dem.formulas.register(tokens)
                self.axioms[shape] = dem.axioms.register(f"deep-{shape}-{suffix}", formula.id).id
            self.theorem = dem.theorems.register(f"deepTheorem{suffix}", base.id, []).id

    def tokens(self, shape, depth):
        ids = [self.neg] * depth + [self.r] if shape == "unary" else [self.imp, self.r] * depth + [self.r]
        return [Token(symbol_id=value) for value in ids]

    def stored_body(self, shape, depth):
        # Test fixture only: create a well-formed formula through the real SQL
        # guards, allowing substitution probes beyond Python registration's
        # recursion ceiling. Never fabricate verified proofs or disable guards.
        tokens = self.tokens(shape, depth)
        with self.api.transaction() as dem:
            public_ids = dem.formulas._load_symbol_public_ids(tokens)
            digest = compute_hash(tokens, public_ids)
            existing = dem.session.scalar(select(Formula.id).where(Formula.hash == digest))
            if existing is not None:
                return existing
            kind = dem.session.scalar(select(FormulaType.id).where(FormulaType.code == "proposition"))
            formula_id = dem.session.scalar(insert(Formula).values(public_id=uuid4().hex, hash=digest,
                                                                   formula_type_id=kind, token_count=len(tokens)).returning(Formula.id))
            dem.session.execute(insert(FormulaToken), [{"formula_id": formula_id, "position": position,
                                                       "symbol_id": token.symbol_id} for position, token in enumerate(tokens)])
            return formula_id

    def payload(self, shape, path, depth):
        tokens = [{"symbol_id": token.symbol_id} for token in self.tokens(shape, depth)]
        if path in {"register", "print"}:
            return "/formulas" if path == "register" else "/formulas/print", {"tokens": tokens}
        if path == "parse":
            expression = "¬(" * depth + "R" + ")" * depth if shape == "unary" else "R → " * depth + "R"
            return "/formulas/parse", {"text": expression, "context": {"R": self.r}}
        body_id = self.stored_body(shape, depth - 1)
        with self.api.transaction() as dem:
            proof_id = dem.proofs.create_proof(self.theorem).id
        return f"/proofs/{proof_id}/steps", {"kind": "axiom", "axiom_id": self.axioms[shape],
                                            "subst": {"prop_substs": [{"source_symbol_id": self.p,
                                                                        "body_formula_id": body_id}]}}


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("shape", ["unary", "right"])
@pytest.mark.parametrize("path", ["register", "print", "parse", "indirect"])
def test_real_deep_formula_is_422_and_atomic(live_api, monkeypatch, enabled, shape, path):
    inputs = DeepInputs(live_api)
    route, body = inputs.payload(shape, path, 1100)
    if enabled:
        monkeypatch.setenv("DEM_BETA", "1")
    before = row_counts(live_api)
    status, response, _ = request("POST", route, body, raise_app_exceptions=False)
    assert status == 422 and response["code"] == "formula.too_deep", (status, response)
    assert row_counts(live_api) == before


@pytest.mark.parametrize("shape", ["unary", "right"])
@pytest.mark.parametrize("path", ["register", "print", "parse", "indirect"])
def test_shallow_formula_remains_accepted(live_api, shape, path):
    inputs = DeepInputs(live_api)
    route, body = inputs.payload(shape, path, 3)
    status, response, _ = request("POST", route, body)
    assert status == (201 if path in {"register", "indirect"} else 200), response
