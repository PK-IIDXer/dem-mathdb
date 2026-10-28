"""Opt-in public-beta boundary; mathematical services remain unchanged.

State is process-local: deploy with exactly one uvicorn worker. Client addresses
come exclusively from ASGI (configure uvicorn's trusted proxy headers in beta3).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from weakref import WeakKeyDictionary

from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError as PydanticValidationError
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.orm import Session
from starlette.routing import Match

from dem.db.models.language import Formula
from dem.db.models.theorem import ProofStep, Theorem, TheoremPremise

log = logging.getLogger("webapi.beta")
SESSION_KEY = "beta_limits"
PROOF_ID = TypeAdapter(int)
PURE_POSTS = frozenset({"/formulas/parse", "/formulas/print"})
# Transport assumptions, verified again in staging; these are not Limits.
PROXY_IDLE_CONNECTION_BUDGET = 32
INTERNAL_CONNECTION_BUDGET = 4
BETA_POOL_TIMEOUT_SECONDS = 2.0
HEAVY_ROUTES = frozenset({
    "/proofs/{id}/steps/suggest", "/proofs/{id}/steps/suggest-backward",
    "/theorems/applicable", "/proofs/{id}/validate", "/formulas/search",
    "/formulas/validate", "/proofs/compute-substituted-tokens",
    "/proofs/compute-gen-tokens", "/workspace/export",
    "/proofs/{id}/is-valid-in-system/{axiom_system_id}",
})


@dataclass(frozen=True)
class Limits:
    body_bytes: int = 256 * 1024
    name: int = 120
    description: int = 4000
    notation: int = 500
    formula_tokens: int = 2000
    proof_steps: int = 500
    theorem_premises: int = 20
    formulas: int = 20_000
    theorems: int = 2000
    steps: int = 40_000
    database_bytes: int = 1024 ** 3
    capacity_interval: float = 60
    read_per_minute: int = 600
    read_burst: int = 300
    write_per_minute: int = 20
    write_per_hour: int = 200
    heavy_per_minute: int = 10
    export_per_ten_minutes: int = 2
    global_write_per_hour: int = 1000
    concurrent: int = 4
    concurrent_wait_seconds: float = 10
    source_waiters: int = 32
    global_waiters: int = 256
    heavy_concurrent: int = 1
    max_clients: int = 100_000


def enabled() -> bool:
    return os.environ.get("DEM_BETA", "").strip().lower() in {"1", "true", "yes"}


def settings(app) -> Limits:
    return getattr(app.state, "beta_limits", Limits())


def source_key(host: str) -> str:
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address):
            if address.ipv4_mapped:
                return str(address.ipv4_mapped)
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
        return str(address)
    except ValueError:
        return host


def category(method: str, route: str) -> str:
    return "read" if method in {"GET", "HEAD", "OPTIONS"} or (method == "POST" and route in PURE_POSTS) else "write"


class BetaReject(Exception):
    def __init__(self, status: int, code: str, detail: str, retry: int | None = None):
        self.status, self.code, self.detail, self.retry = status, code, detail, retry


class LimitExceeded(BetaReject):
    def __init__(self, limit: str, maximum: int):
        super().__init__(422, "beta.limit_exceeded", f"{limit} exceeds beta limit {maximum}")
        self.limit, self.maximum = limit, maximum


class SourceBusy(BetaReject):
    def __init__(self):
        super().__init__(429, "beta.rate_limited", "Too many concurrent requests", 1)


def reject_response(exc: BetaReject, route: str, kind: str):
    log.warning("beta_reject category=%s code=%s route=%s", kind, exc.code, route)
    body = {"detail": exc.detail, "code": exc.code}
    if isinstance(exc, LimitExceeded):
        body.update(limit=exc.limit, maximum=exc.maximum)
    return JSONResponse(status_code=exc.status, content=body,
                        headers={"Retry-After": str(exc.retry)} if exc.retry is not None else None)


@dataclass
class Client:
    active: int = 0
    buckets: dict = field(default_factory=dict)
    waiters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Admission:
    client: str
    heavy: bool


class Runtime:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = Lock()
        self.capacity_lock = Lock()
        self.clients: OrderedDict[str, Client] = OrderedDict()
        self.global_buckets = {}
        self.capacity = WeakKeyDictionary()
        self.proof_writes = set()
        self.active_heavy = 0
        self.waiting = 0

    def enter(self, host: str, kind: str, route: str, limits: Limits, resource=None):
        key, now = source_key(host), self.clock()
        with self.lock:
            client = self.clients.get(key)
            if client is None:
                while len(self.clients) >= limits.max_clients:
                    idle = next((k for k, value in self.clients.items() if not value.active and not value.waiters), None)
                    if idle is None:
                        raise BetaReject(429, "beta.rate_limited", "Client capacity reached", 1)
                    del self.clients[idle]
                client = self.clients[key] = Client()
            self.clients.move_to_end(key)
            if client.active >= limits.concurrent:
                raise SourceBusy()
            heavy = route in HEAVY_ROUTES
            if heavy and self.active_heavy >= limits.heavy_concurrent:
                raise BetaReject(429, "beta.busy", "Heavy processing is busy", 2)
            if resource is not None and resource in self.proof_writes:
                raise BetaReject(409, "beta.write_conflict", "Proof is being edited")
            specs = [(client.buckets, "read", limits.read_burst, limits.read_per_minute / 60)] if kind == "read" else [
                (client.buckets, "write_minute", limits.write_per_minute, limits.write_per_minute / 60),
                (client.buckets, "write_hour", limits.write_per_hour, limits.write_per_hour / 3600),
                (self.global_buckets, "write_hour", limits.global_write_per_hour, limits.global_write_per_hour / 3600),
            ]
            if route in HEAVY_ROUTES:
                specs.append((client.buckets, "heavy", limits.heavy_per_minute, limits.heavy_per_minute / 60))
            if route == "/workspace/export":
                specs.append((client.buckets, "export", limits.export_per_ten_minutes, limits.export_per_ten_minutes / 600))
            pending, wait = [], 0
            for buckets, name, burst, rate in specs:
                tokens, previous = buckets.get(name, (float(burst), now))
                tokens = min(burst, tokens + max(0, now - previous) * rate)
                if tokens < 1:
                    wait = max(wait, math.ceil((1 - tokens) / rate) if rate else 3600)
                pending.append((buckets, name, tokens))
            if wait:
                raise BetaReject(429, "beta.rate_limited", "Beta request rate exceeded", max(1, wait))
            for buckets, name, tokens in pending:
                buckets[name] = (tokens - 1, now)
            client.active += 1
            if heavy:
                self.active_heavy += 1
            if resource is not None:
                self.proof_writes.add(resource)
        return Admission(key, heavy)

    async def enter_async(self, host: str, kind: str, route: str, limits: Limits, resource=None):
        """Wait only for source concurrency, without reserving a worker thread.

        Register under the same lock as leave, preventing lost notifications.
        Waiting clients are pinned in the bounded LRU; cancellation, timeout and
        admission all unregister in finally. Buckets are spent only by enter.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limits.concurrent_wait_seconds
        signal = asyncio.Event()
        client = None
        key = source_key(host)
        try:
            while True:
                if client is not None and loop.time() >= deadline:
                    raise SourceBusy()
                signal.clear()
                try:
                    return self.enter(host, kind, route, limits, resource)
                except SourceBusy:
                    with self.lock:
                        current = self.clients.get(key)
                        if current is None or current.active < limits.concurrent:
                            continue
                        if client is None:
                            if len(current.waiters) >= limits.source_waiters or self.waiting >= limits.global_waiters:
                                raise BetaReject(429, "beta.rate_limited", "Concurrency wait queue is full", 1)
                            client = current
                            client.waiters[signal] = loop
                            self.waiting += 1
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise SourceBusy()
                    try:
                        await asyncio.wait_for(signal.wait(), remaining)
                    except TimeoutError:
                        raise SourceBusy() from None
        finally:
            if client is not None:
                with self.lock:
                    del client.waiters[signal]
                    self.waiting -= 1

    def leave(self, admission: Admission, resource=None):
        with self.lock:
            self.clients[admission.client].active -= 1
            if admission.heavy:
                self.active_heavy -= 1
            if resource is not None:
                self.proof_writes.discard(resource)
            for signal, loop in self.clients[admission.client].waiters.items():
                loop.call_soon_threadsafe(signal.set)

    def is_full(self, engine, limits: Limits, *, force=False):
        with self.capacity_lock:
            now = self.clock()
            cached = self.capacity.get(engine)
            if not force and cached is not None and cached[0] == limits and now - cached[1] < limits.capacity_interval:
                return cached[2]
            with engine.connect() as connection:
                full = any(connection.scalar(select(func.count()).select_from(model)) >= maximum
                           for model, maximum in [(Formula, limits.formulas), (Theorem, limits.theorems), (ProofStep, limits.steps)])
                if engine.dialect.name == "sqlite":
                    size = connection.scalar(text("PRAGMA page_count")) * connection.scalar(text("PRAGMA page_size"))
                else:
                    size = connection.scalar(text("SELECT pg_database_size(current_database())"))
            full = full or size >= limits.database_bytes
            self.capacity[engine] = (limits, now, full)
            return full


runtime = Runtime()


def maintenance() -> bool:
    directory = os.environ.get("DEM_BETA_FLAG_DIR")
    return bool(directory and (Path(directory) / "read_only").is_file())


def write_state(engine, limits):
    if maintenance():
        return "maintenance"
    return "full" if runtime.is_full(engine, limits) else "open"


def last_reset_error():
    try:
        path = Path(os.environ["DEM_BETA_STATUS_FILE"]).with_name("reset-error.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"failed_at", "stage"}:
            return None
        if data["stage"] not in ("prepare", "stop", "swap", "start", "ready", "finish", "restore"):
            return None
        value = data["failed_at"]
        if not isinstance(value, str) or datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            return None
        return data
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        return None


def reset_status():
    result = {"last_reset_at": None, "next_reset_at": None}
    try:
        data = json.loads(Path(os.environ["DEM_BETA_STATUS_FILE"]).read_text(encoding="utf-8"))
        for key in result:
            value = data.get(key)
            if isinstance(value, str):
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                result[key] = value
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        result = {key: None for key in result}
    return {**result, "last_reset_error": last_reset_error()}


class BetaMiddleware:
    def __init__(self, app, owner):
        self.app, self.owner = app, owner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not enabled():
            return await self.app(scope, receive, send)
        route, child = "<unmatched>", {}
        candidates = []
        for included in self.owner.router.routes:
            if hasattr(included, "effective_route_contexts"):
                candidates.extend(included.effective_route_contexts())
            else:
                candidates.append(included)
        for candidate in candidates:
            match, found = candidate.matches(scope)
            if match == Match.FULL:
                route, child = candidate.path, found
                break
        kind = category(scope["method"], route)
        is_contact = scope["method"] == "POST" and route == "/contact"
        if is_contact:
            kind = "contact"
        limits = settings(self.owner)
        scope.setdefault("state", {})["beta_category"] = kind
        scope["state"]["beta_route"] = route
        # Preserve the existing read-only response and give it first priority.
        from webapi.deps import is_read_only
        if kind == "write" and is_read_only():
            return await self.app(scope, receive, send)
        key = None
        resource = child.get("path_params", {}).get("id") if scope["method"] == "POST" and route == "/proofs/{id}/steps" else None
        if resource is not None:
            try:
                resource = PROOF_ID.validate_python(resource)
            except PydanticValidationError:
                resource = None  # Let the route return its ordinary input error.
        try:
            if route in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
                await JSONResponse(status_code=404, content={"detail": "Not Found"})(scope, receive, send)
                return
            if scope["method"] == "POST" and route == "/symbol-roles":
                raise BetaReject(403, "beta.disabled", "Symbol role assignment is disabled in beta")
            if scope["method"] == "GET" and route == "/workspace/export":
                raise BetaReject(403, "beta.disabled", "Workspace export is disabled in beta")
            if kind == "write" and maintenance():
                raise BetaReject(503, "beta.maintenance", "Beta is under maintenance")
            if not is_contact:
                key = await runtime.enter_async((scope.get("client") or ("unknown", 0))[0], kind, route, limits, resource)
            for name, value in scope.get("headers", []):
                if name.lower() == b"content-length":
                    try:
                        oversized = int(value) > limits.body_bytes
                    except ValueError:
                        oversized = False
                    if oversized:
                        raise BetaReject(413, "beta.body_too_large", "Beta request body limit exceeded")
            # Count on receive, before dispatch: even an endpoint ignoring its
            # body cannot bypass this limit or commit before a late oversized chunk.
            payload = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                piece = message.get("body", b"")
                if len(payload) + len(piece) > limits.body_bytes:
                    raise BetaReject(413, "beta.body_too_large", "Beta request body limit exceeded")
                payload.extend(piece)
                if not message.get("more_body", False):
                    break
            iterator = iter([{"type": "http.request", "body": bytes(payload), "more_body": False}])
            async def replay():
                try:
                    return next(iterator)
                except StopIteration:
                    return await receive()
            await self.app(scope, replay, send)
        except BetaReject as exc:
            await reject_response(exc, route, kind)(scope, receive, send)
        finally:
            if key is not None:
                runtime.leave(key, resource)


@event.listens_for(Session, "before_flush")
def enforce_content_limits(session, flush_context, instances):
    limits = session.info.get(SESSION_KEY)
    if limits is None:
        return
    with session.no_autoflush:
        for row in list(session.new) + list(session.dirty):
            state = inspect(row)
            for column in state.mapper.columns:
                name = column.key
                if state.mapper.local_table.name == "namespace":
                    continue
                if row not in session.new and not state.attrs[name].history.has_changes():
                    continue
                maximum = (limits.name if name in {"name", "alias", "title"} else
                           limits.description if name in {"description", "remarks"} else
                           limits.notation if name == "latex_template" else None)
                value = getattr(row, name)
                if maximum is not None and isinstance(value, str) and len(value) > maximum:
                    raise LimitExceeded(name, maximum)
            if isinstance(row, Formula) and row.token_count > limits.formula_tokens:
                raise LimitExceeded("formula_tokens", limits.formula_tokens)
        for model, parent, maximum, label in [
            (ProofStep, "proof_id", limits.proof_steps, "proof_steps"),
            (TheoremPremise, "theorem_id", limits.theorem_premises, "theorem_premises"),
        ]:
            new = [row for row in session.new if isinstance(row, model)]
            dirty = [row for row in session.dirty if isinstance(row, model)]
            changes = []
            for row in dirty:
                history = inspect(row).attrs[parent].history
                if history.has_changes():
                    changes.extend((value, 1) for value in history.added)
                    changes.extend((value, -1) for value in history.deleted)
            parents = {getattr(row, parent) for row in new + dirty} | {value for value, _ in changes}
            for parent_id in parents:
                count = session.scalar(select(func.count()).select_from(model).where(getattr(model, parent) == parent_id))
                count += sum(getattr(row, parent) == parent_id for row in new)
                count += sum(delta for value, delta in changes if value == parent_id)
                count -= sum(isinstance(row, model) and getattr(row, parent) == parent_id for row in session.deleted)
                if count > maximum:
                    raise LimitExceeded(label, maximum)
