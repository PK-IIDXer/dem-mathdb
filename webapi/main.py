from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from webapi.deps import (
    close_database_connections,
    initialize_on_startup,
    is_read_only,
)
from webapi.errors import register_exception_handlers
from webapi import contact
from webapi.beta import BetaMiddleware, PURE_POSTS
from webapi.routers import (
    axioms,
    definitions,
    explorations,
    formulas,
    proofs,
    stats,
    symbols,
    tags,
    theorems,
    workspace,
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
READ_ONLY_POST_PATHS = PURE_POSTS


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_on_startup()
    try:
        yield
    finally:
        close_database_connections()


app = FastAPI(title="Deus Ex Machina API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Next-Cursor"],
)

# Formula token lists are long and extremely repetitive, so compression is
# effective. Nothing in front of uvicorn compresses today.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def enforce_read_only(request: Request, call_next):
    """Reject write requests when DEM_READ_ONLY is set (view-only public deployment)."""
    # parse/print carry potentially long text and a context mapping, so POST is
    # retained to avoid URL length limits even though these operations do not
    # write. Suggest is deliberately absent: it interns inferred formulas.
    is_pure_formula_post = (
        request.method == "POST" and request.url.path in READ_ONLY_POST_PATHS
    )
    is_contact = request.method == "POST" and request.url.path == "/contact"
    if request.method not in SAFE_METHODS and not is_pure_formula_post and not is_contact and is_read_only():
        return JSONResponse(status_code=403, content={"detail": "read-only mode: write operations are disabled"})
    return await call_next(request)


register_exception_handlers(app)

app.include_router(stats.router)
app.include_router(symbols.router)
app.include_router(formulas.router)
app.include_router(axioms.router)
app.include_router(theorems.router)
app.include_router(proofs.router)
app.include_router(definitions.router)
app.include_router(explorations.router)
app.include_router(tags.router)
app.include_router(workspace.router)
app.include_router(contact.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def ready(request: Request):
    from sqlalchemy import text
    from sqlalchemy.exc import TimeoutError as PoolTimeoutError
    from webapi.deps import get_workspace_request_context, resolve_request_account
    try:
        context = get_workspace_request_context(request, resolve_request_account(request))
        with context.api.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except PoolTimeoutError as exc:
        from webapi.beta import enabled
        if enabled() and exc.code == "3o7r":
            return JSONResponse(status_code=503, content={"status": "unavailable", "code": "beta.database_busy"},
                                headers={"Retry-After": "2"})
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


@app.get("/config")
def config(request: Request) -> dict[str, object]:
    from dataclasses import asdict
    from webapi.beta import enabled, reset_status, settings, write_state
    from webapi.deps import get_workspace_request_context, resolve_request_account
    result = {"read_only": is_read_only()}
    if enabled():
        context = get_workspace_request_context(request, resolve_request_account(request))
        limits = settings(request.app)
        result["beta"] = {"enabled": True, "write_state": write_state(context.api.engine, limits),
                          **reset_status(), "limits": asdict(limits)}
    return result


app.add_middleware(BetaMiddleware, owner=app)
