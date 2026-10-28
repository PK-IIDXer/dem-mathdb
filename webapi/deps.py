from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from dem.api import DemApi, DemServices
from dem.db.triggers import INCOMPLETE_FORMULAS_SQL
from webapi.management.database import (
    create_management_engine,
    ensure_development_account,
    upgrade_management_schema,
)
from webapi.management.deployment_lock import (
    DeploymentLock,
    deployment_lock_path,
)
from webapi.management.models import Workspace
from webapi.management.schema_revision import content_schema_head
from webapi.management.schema_state import READY
from webapi.management.workspace import (
    DEFAULT_WORKSPACE_TEMPLATE_PATH,
    validate_workspace_template,
)

DEFAULT_SQLITE_URL = "sqlite:///./dem_dev.db"
MANAGEMENT_DATABASE_ENV = "DEM_MANAGEMENT_DATABASE_URL"
WORKSPACE_TEMPLATE_ENV = "DEM_WORKSPACE_TEMPLATE_PATH"
WORKSPACE_HEADER = "X-Workspace-ID"
WORKSPACE_ENGINE_CACHE_MAX_SIZE = 16
DEVELOPMENT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEVELOPMENT_EXTERNAL_SUBJECT = "development:single-account"
_LEGACY_WORKSPACE_KEY = "legacy-single-database"
LOCAL_WORKSPACE_NAMESPACE = "local.workspace"
_API_LOCAL_NAMESPACE_KEY = "api_local_namespace"


def _database_url() -> str:
    return os.environ.get("DEM_DATABASE_URL", DEFAULT_SQLITE_URL)


def _management_database_url() -> str | None:
    value = os.environ.get(MANAGEMENT_DATABASE_ENV, "").strip()
    return value or None


def _workspace_template_path() -> Path:
    value = os.environ.get(WORKSPACE_TEMPLATE_ENV, "").strip()
    return Path(value) if value else DEFAULT_WORKSPACE_TEMPLATE_PATH


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def is_read_only() -> bool:
    """Deployment-wide switch that blocks all write requests (see webapi/main.py)."""
    return os.environ.get("DEM_READ_ONLY", "false").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class RequestAccount:
    """Account identity resolved at the request boundary, before authorization."""

    id: UUID


@dataclass(frozen=True)
class WorkspaceRequestContext:
    """Owned workspace metadata and its isolated content-database API."""

    workspace_id: UUID
    slug: str
    title: str | None
    local_namespace_name: str
    api: DemApi


@dataclass
class _CachedWorkspaceApi:
    storage_uri: str
    api: DemApi


class WorkspaceApiCache:
    """Thread-safe LRU of workspace engines; evicted pools are disposed."""

    def __init__(self, max_size: int = WORKSPACE_ENGINE_CACHE_MAX_SIZE) -> None:
        if max_size < 1:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self._entries: OrderedDict[str, _CachedWorkspaceApi] = OrderedDict()
        self._lock = RLock()

    def get(
        self,
        workspace_key: str,
        storage_uri: str,
        *,
        required_revision: str | None = None,
    ) -> DemApi:
        with self._lock:
            cached = self._entries.get(workspace_key)
            if cached is not None and cached.storage_uri == storage_uri:
                self._entries.move_to_end(workspace_key)
                return cached.api
            if cached is not None:
                self._entries.pop(workspace_key)
                cached.api.engine.dispose()

            connect_args = (
                {"check_same_thread": False} if _is_sqlite(storage_uri) else {}
            )
            from sqlalchemy.engine import make_url
            from webapi.beta import enabled, BETA_POOL_TIMEOUT_SECONDS
            # In-memory SQLite uses SingletonThreadPool, which has no checkout
            # wait timeout. File SQLite and PostgreSQL use QueuePool by default.
            queue_pool = not _is_sqlite(storage_uri) or make_url(storage_uri).database not in (None, "", ":memory:")
            pool_options = {"pool_timeout": BETA_POOL_TIMEOUT_SECONDS} if enabled() and queue_pool else {}
            api = DemApi.from_url(storage_uri, connect_args=connect_args, **pool_options)
            try:
                with api.engine.connect() as connection:
                    if required_revision is not None:
                        embedded = connection.scalar(
                            text("SELECT version_num FROM alembic_version")
                        )
                        if embedded != required_revision:
                            raise RuntimeError(
                                "workspace schema revision is not ready for this API"
                            )
                        incomplete = list(
                            connection.execute(text(INCOMPLETE_FORMULAS_SQL))
                        )
                        if incomplete:
                            formula_id = incomplete[0][0]
                            raise RuntimeError(
                                f"workspace has incomplete formula {formula_id}"
                            )
            except Exception:
                api.engine.dispose()
                raise
            self._entries[workspace_key] = _CachedWorkspaceApi(storage_uri, api)
            # Known Phase 3 constraint: get() returns before the request opens its
            # transaction, so > max_size simultaneous resolutions can evict an API
            # another request still holds. dispose() leaves checked-out connections
            # alive, but this cache needs leases before multi-workspace concurrency.
            while len(self._entries) > self.max_size:
                _, evicted = self._entries.popitem(last=False)
                evicted.api.engine.dispose()
            return api

    def close(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.api.engine.dispose()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


@dataclass
class _ManagementRuntime:
    database_url: str
    engine: Engine
    session_factory: sessionmaker[Session]


_workspace_api_cache = WorkspaceApiCache()
_management_runtime: _ManagementRuntime | None = None
_management_lock = RLock()
_deployment_lock: DeploymentLock | None = None


def _get_management_runtime(database_url: str) -> _ManagementRuntime:
    global _management_runtime
    with _management_lock:
        if (
            _management_runtime is not None
            and _management_runtime.database_url == database_url
        ):
            return _management_runtime
        if _management_runtime is not None:
            _management_runtime.engine.dispose()
        engine = create_management_engine(database_url)
        _management_runtime = _ManagementRuntime(
            database_url=database_url,
            engine=engine,
            session_factory=sessionmaker(engine, expire_on_commit=False),
        )
        return _management_runtime


def resolve_request_account(request: Request) -> RequestAccount:
    """Phase 3 account seam; an external IdP dependency replaces this in Phase 4."""
    del request
    return RequestAccount(id=DEVELOPMENT_ACCOUNT_ID)


def _workspace_for_request(
    request: Request, account: RequestAccount, session: Session
) -> Workspace:
    requested_id = request.headers.get(WORKSPACE_HEADER)
    if requested_id is not None:
        try:
            workspace_id = UUID(requested_id)
        except ValueError:
            workspace_id = None
        workspace = (
            session.scalar(
                select(Workspace).where(
                    Workspace.id == workspace_id,
                    Workspace.account_id == account.id,
                )
            )
            if workspace_id is not None
            else None
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    workspaces = list(
        session.scalars(
            select(Workspace)
            .where(Workspace.account_id == account.id)
            .order_by(Workspace.created_at, Workspace.id)
            .limit(2)
        )
    )
    if not workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if len(workspaces) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Select a workspace with the {WORKSPACE_HEADER} header",
        )
    return workspaces[0]


def get_workspace_request_context(
    request: Request,
    account: RequestAccount = Depends(resolve_request_account),
) -> WorkspaceRequestContext:
    """Resolve a request to exactly one owned workspace and its isolated API."""
    management_url = _management_database_url()
    if management_url is None:
        return WorkspaceRequestContext(
            workspace_id=UUID(int=0),
            slug="export",
            title=None,
            local_namespace_name=LOCAL_WORKSPACE_NAMESPACE,
            api=_workspace_api_cache.get(_LEGACY_WORKSPACE_KEY, _database_url()),
        )

    runtime = _get_management_runtime(management_url)
    with runtime.session_factory() as session:
        workspace = _workspace_for_request(request, account, session)
        expected_revision = content_schema_head()
        if (
            workspace.schema_state != READY
            or workspace.schema_revision != expected_revision
        ):
            raise HTTPException(
                status_code=503,
                detail="Workspace schema is not ready",
            )
        workspace_key = str(workspace.id)
        storage_uri = workspace.storage_uri
        workspace_id = workspace.id
        slug = workspace.slug
        title = workspace.title
    try:
        api = _workspace_api_cache.get(
            workspace_key,
            storage_uri,
            required_revision=expected_revision,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Workspace schema health check failed",
        ) from exc
    return WorkspaceRequestContext(
        workspace_id=workspace_id,
        slug=slug,
        title=title,
        local_namespace_name=f"local.ws-{workspace_id.hex}",
        api=api,
    )


def get_dem_api(
    request: Request,
    account: RequestAccount = Depends(resolve_request_account),
) -> DemApi:
    """Resolve a request to the engine for exactly one owned workspace."""
    return get_workspace_request_context(request, account).api


def initialize_on_startup() -> None:
    """Initialize the configured management or legacy single-database deployment.

    A management DB is upgraded through its dedicated Alembic history and gets the
    fixed Phase 3 development account. Without one, the legacy SQLite path still
    creates the content schema and seeds it idempotently.
    Beta instead checks an already prepared single database without bootstrapping.

    Content-database Tier A immutability triggers are installed by both Alembic
    and ``Base.metadata.create_all()`` from the shared definitions in
    ``dem.db.triggers``.
    """
    global _deployment_lock
    management_url = _management_database_url()
    from webapi.beta import enabled

    if enabled():
        # Beta databases are prepared offline by their owner. Never bootstrap
        # them with the restricted runtime role, including a misconfigured
        # management deployment.
        try:
            if management_url is not None:
                raise RuntimeError("beta requires a single prepared database")
            api = _workspace_api_cache.get(_LEGACY_WORKSPACE_KEY, _database_url())
            with api.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                revisions = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
                if revisions != [content_schema_head()]:
                    raise RuntimeError("schema is not ready")
                if connection.execute(text(INCOMPLETE_FORMULAS_SQL)).first() is not None:
                    raise RuntimeError("formulas are not complete")
        except Exception:
            raise RuntimeError("Beta database startup check failed") from None
        return
    # Only management-DB deployments have workspace DBs that the schema updater
    # rewrites.  The legacy single-database mode has nothing for the updater to
    # touch, so it takes no deployment lock.
    if management_url is not None and _deployment_lock is None:
        _deployment_lock = DeploymentLock(
            deployment_lock_path(management_url), exclusive=False
        )
        try:
            _deployment_lock.acquire()
        except BaseException:
            _deployment_lock = None
            raise
    try:
        if management_url is not None:
            validate_workspace_template(_workspace_template_path())
            upgrade_management_schema(management_url)
            runtime = _get_management_runtime(management_url)
            with runtime.session_factory.begin() as session:
                ensure_development_account(
                    session,
                    account_id=DEVELOPMENT_ACCOUNT_ID,
                    external_subject=DEVELOPMENT_EXTERNAL_SUBJECT,
                    display_name="Development account",
                )
            return

        api = _workspace_api_cache.get(_LEGACY_WORKSPACE_KEY, _database_url())
        if _is_sqlite(_database_url()):
            api.create_schema()
        api.seed_core()
    except BaseException:
        if _deployment_lock is not None:
            _deployment_lock.release()
            _deployment_lock = None
        raise


def dem_services(
    request: Request,
    context: WorkspaceRequestContext = Depends(get_workspace_request_context),
) -> Iterator[DemServices]:
    """One request transaction; callers use function scope to commit before send.

    Keep the transaction around endpoint execution and response serialization.
    Deferred database guards must finish before any successful response is sent.
    """
    with context.api.transaction() as dem:
        dem.session.info[_API_LOCAL_NAMESPACE_KEY] = context.local_namespace_name
        from webapi.beta import BetaReject, SESSION_KEY, enabled, settings, write_state
        if enabled():
            limits = settings(request.app)
            dem.session.info[SESSION_KEY] = limits
            if getattr(request.state, "beta_category", "read") == "write":
                state = write_state(context.api.engine, limits)
                if state != "open":
                    raise BetaReject(503, f"beta.{state}", f"Beta write state: {state}")
        yield dem


def get_local_namespace_name(
    dem: DemServices = Depends(dem_services, scope="function"),
) -> str:
    """The namespace for entities authored by this API request."""
    return str(
        dem.session.info.get(_API_LOCAL_NAMESPACE_KEY, LOCAL_WORKSPACE_NAMESPACE)
    )


def close_database_connections() -> None:
    """Dispose cached workspace pools and the management database pool."""
    global _management_runtime, _deployment_lock
    _workspace_api_cache.close()
    with _management_lock:
        runtime = _management_runtime
        _management_runtime = None
    if runtime is not None:
        runtime.engine.dispose()
    lock, _deployment_lock = _deployment_lock, None
    if lock is not None:
        lock.release()
