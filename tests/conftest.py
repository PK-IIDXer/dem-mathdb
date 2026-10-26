"""Shared seed snapshots for the logical content test suite.

The logical seed cascade is expensive enough that rebuilding it in every test
module dominates the pytest runtime.  Build each layer once per test session
and persist it by production-code fingerprint.  SQLite modules receive an
isolated writable file copy; PostgreSQL modules share a template database and
run inside an outer transaction that is rolled back at teardown.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
import warnings
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from filelock import FileLock, Timeout
from psycopg.errors import InvalidCatalogName
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language


from dem.db.seeds import seed_public_core, seed_all

SeedFunction = Callable[[Session], object]

_SNAPSHOT_CACHE_VERSION = "2"
_TEST_DATABASE_ENV = "DEM_TEST_DATABASE"
_DATABASE_URL_ENV = "DEM_DATABASE_URL"
_POSTGRES_ADMIN_URL = "postgresql+psycopg://dem_dev@localhost:5432/postgres"
_POSTGRES_DATABASE_NAME = re.compile(r"^[a-z0-9_]+$")
_POSTGRES_SNAPSHOT_NAME = re.compile(r"^pub_seed_([0-9a-f]{20})_.+$")
_POSTGRES_WORKER_NAME = re.compile(
    r"^pub_tw_([0-9a-f]{8})_([0-9a-f]{8})_([a-z0-9]+)_(.+)$"
)
_POSTGRES_TEMP_NAME = re.compile(
    r"^pub_seed_tmp_([0-9a-f]{8})_([0-9a-f]{8})_([0-9a-z]{2})_[0-9a-f]{6}$"
)
_SQLITE_SNAPSHOT_LOCK_TIMEOUT_SECONDS = 300
_POSTGRES_TEMPLATE_LOCK_TIMEOUT_SECONDS = 300
_POSTGRES_RUN_ID_ENV = "DEM_TEST_RUN_ID"
_POSTGRES_METRICS_DIR_ENV = "DEM_TEST_PG_METRICS_DIR"

_PHASES: tuple[tuple[str, SeedFunction], ...] = (
    ("public_core", seed_public_core),
    ("public_demo", seed_all),
)
_BRANCHES: tuple[tuple[str, str, SeedFunction], ...] = ()


def _phase_plan(phase: str) -> tuple[str | None, SeedFunction, int]:
    """The parent phase (None for the first), seed function and build index."""
    phase_names = [name for name, _ in _PHASES]
    if phase in phase_names:
        index = phase_names.index(phase)
        return (phase_names[index - 1] if index else None, _PHASES[index][1], index)
    for offset, (name, parent, seed_function) in enumerate(_BRANCHES):
        if name == phase:
            return parent, seed_function, len(_PHASES) + offset
    raise ValueError(f"unknown seed phase: {phase!r}")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "timing_sensitive: wall-clock threshold test that must run without xdist",
    )
    configured_database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    if configured_database == "postgresql":
        # pytest_configure runs in the controller before xdist starts workers, so
        # they inherit one run id while retaining distinct worker ids.
        os.environ.setdefault(_POSTGRES_RUN_ID_ENV, uuid.uuid4().hex[:8])


def _file_engine(path: Path) -> Engine:
    return create_engine(f"sqlite+pysqlite:///{path.as_posix()}")


def _upgrade_schema(database_url: URL) -> None:
    """Build a test schema through the same Alembic entry point as deployment."""
    repository = Path(__file__).resolve().parents[1]
    config = Config(str(repository / "alembic.ini"))
    # Fixture schema setup must not disable the application/pytest loggers.
    config.config_file_name = None
    config.set_main_option("script_location", str(repository / "alembic"))
    previous_url = os.environ.get(_DATABASE_URL_ENV)
    os.environ[_DATABASE_URL_ENV] = database_url.render_as_string(
        hide_password=False
    )
    try:
        command.upgrade(config, "head")
    finally:
        if previous_url is None:
            os.environ.pop(_DATABASE_URL_ENV, None)
        else:
            os.environ[_DATABASE_URL_ENV] = previous_url


def _build_model_l2(engine: Engine) -> None:
    """Build the cached create_all-origin side of the public comparison."""
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        for _, seed_function in _PHASES[:3]:
            seed_function(session)
        session.commit()


@dataclass
class SQLiteSeedSnapshotFactory:
    root: Path
    paths: dict[str, Path] = field(default_factory=dict)

    def get(self, phase: str) -> Path:
        parent, seed_function, _ = _phase_plan(phase)
        if phase in self.paths:
            return self.paths[phase]

        path = self.root / f"seed-{phase}.db"
        if self._is_valid(path):
            self.paths[phase] = path
            return path

        previous = self.get(parent) if parent is not None else None
        with self._lock(path.with_suffix(path.suffix + ".lock")):
            if self._is_valid(path):
                self.paths[phase] = path
                return path

            temporary = path.with_name(
                f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            )
            try:
                if previous is None:
                    self._build_first(temporary, seed_function)
                else:
                    shutil.copy2(previous, temporary)
                    self._extend(temporary, seed_function)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        self.paths[phase] = path
        return path

    def get_model_l2(self) -> Path:
        key = "model_l2"
        if key in self.paths:
            return self.paths[key]

        path = self.root / "model-public.db"
        if self._is_valid(path):
            self.paths[key] = path
            return path

        with self._lock(path.with_suffix(path.suffix + ".lock")):
            if self._is_valid(path):
                self.paths[key] = path
                return path

            temporary = path.with_name(
                f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            )
            try:
                engine = _file_engine(temporary)
                try:
                    _build_model_l2(engine)
                finally:
                    engine.dispose()
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        self.paths[key] = path
        return path

    @contextmanager
    def _lock(self, lock_path: Path) -> Iterator[None]:
        try:
            with FileLock(
                lock_path,
                timeout=_SQLITE_SNAPSHOT_LOCK_TIMEOUT_SECONDS,
            ):
                yield
        except Timeout as error:
            worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
            raise RuntimeError(
                f"process {os.getpid()} ({worker}) timed out after "
                f"{_SQLITE_SNAPSHOT_LOCK_TIMEOUT_SECONDS}s waiting for "
                f"SQLite snapshot lock {lock_path}"
            ) from error

    @staticmethod
    def _is_valid(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            with sqlite3.connect(path) as connection:
                return connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        except sqlite3.DatabaseError:
            return False

    @staticmethod
    def _build_first(path: Path, seed_function: SeedFunction) -> None:
        engine = _file_engine(path)
        try:
            _upgrade_schema(engine.url)
            with Session(engine) as session:
                seed_language(session)
                seed_inference_rules(session)
                seed_function(session)
                session.commit()
        finally:
            engine.dispose()

    @staticmethod
    def _extend(path: Path, seed_function: SeedFunction) -> None:
        engine = _file_engine(path)
        try:
            with Session(engine) as session:
                seed_function(session)
                session.commit()
        finally:
            engine.dispose()

    @contextmanager
    def session(self, phase: str) -> Iterator[Session]:
        engine, session, path = _copy_snapshot(self.get(phase))
        try:
            yield session
        finally:
            _close_snapshot_copy(engine, session, path)

    @contextmanager
    def model_l2_session(self) -> Iterator[Session]:
        engine, session, path = _copy_snapshot(self.get_model_l2())
        try:
            yield session
        finally:
            _close_snapshot_copy(engine, session, path)


def _postgres_database_url(admin_url: URL, database: str) -> URL:
    return admin_url.set(database=database)


def _quote_postgres_database(name: str) -> str:
    if not _POSTGRES_DATABASE_NAME.fullmatch(name):
        raise ValueError(f"unsafe PostgreSQL database name: {name!r}")
    return f'"{name}"'


def _postgres_advisory_key(namespace: str, value: str) -> int:
    digest = hashlib.sha256(f"dem-public-tests:{namespace}:{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def _postgres_worker_database_name(
    fingerprint: str,
    run_id: str,
    worker_id: str,
    phase: str,
) -> str:
    safe_worker = re.sub(r"[^a-z0-9]", "", worker_id.lower()) or "main"
    name = f"pub_tw_{fingerprint[:8]}_{run_id[:8]}_{safe_worker[:4]}_{phase}"
    if len(name) > 63:
        raise ValueError(f"PostgreSQL worker database name is too long: {name!r}")
    if not _POSTGRES_WORKER_NAME.fullmatch(name):
        raise ValueError(f"unsafe PostgreSQL worker database name: {name!r}")
    return name


@dataclass
class PostgreSQLSeedSnapshotFactory:
    fingerprint: str
    admin_url: URL = field(default_factory=lambda: make_url(_POSTGRES_ADMIN_URL))
    run_id: str = field(
        default_factory=lambda: os.environ.get(
            _POSTGRES_RUN_ID_ENV, uuid.uuid4().hex[:8]
        )
    )
    worker_id: str = field(
        default_factory=lambda: os.environ.get("PYTEST_XDIST_WORKER", "main")
    )
    names: dict[str, str] = field(default_factory=dict)
    worker_names: dict[str, str] = field(default_factory=dict)
    clone_metrics: list[dict[str, object]] = field(default_factory=list)
    template_build_metrics: list[dict[str, object]] = field(default_factory=list)
    admin_engine: Engine = field(init=False)
    run_lock_connection: object = field(init=False, default=None)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{8}", self.run_id):
            raise ValueError(f"invalid PostgreSQL test run id: {self.run_id!r}")
        self.admin_engine = create_engine(
            self.admin_url,
            isolation_level="AUTOCOMMIT",
            poolclass=NullPool,
        )
        self.run_lock_connection = self.admin_engine.connect()
        self.run_lock_connection.exec_driver_sql(
            "SELECT pg_advisory_lock_shared(%s)",
            (_postgres_advisory_key("run", self.run_id),),
        )
        self._drop_stale_generations()

    def close(self) -> None:
        for name in reversed(list(self.worker_names.values())):
            self._drop_database_best_effort(name, "worker shutdown")
        try:
            self._write_clone_metrics()
        except BaseException as error:
            warnings.warn(
                f"could not write PostgreSQL clone metrics: {error!r}",
                RuntimeWarning,
                stacklevel=2,
            )
        self.worker_names.clear()
        if self.run_lock_connection is not None:
            self.run_lock_connection.exec_driver_sql(
                "SELECT pg_advisory_unlock_shared(%s)",
                (_postgres_advisory_key("run", self.run_id),),
            )
            self.run_lock_connection.close()
            self.run_lock_connection = None
        self.admin_engine.dispose()

    def get(self, phase: str) -> str:
        parent, seed_function, index = _phase_plan(phase)
        if phase in self.names:
            return self.names[phase]

        name = f"pub_seed_{self.fingerprint}_{phase}"
        if len(name) > 63:
            raise ValueError(f"PostgreSQL database name is too long: {name!r}")
        if self._database_exists(name):
            # Cached lookups also ALTER pg_database; serialize that catalog row.
            with self._template_lock(phase):
                if self._database_exists(name):
                    self._set_allow_connections(name, False)
                    self.names[phase] = name
                    return name

        # Finish the predecessor before taking this phase's lock.  Holding only
        # one advisory lock prevents lock-order cycles across cold workers.
        previous = self.get(parent) if parent is not None else None
        with self._template_lock(phase):
            if self._database_exists(name):
                self._set_allow_connections(name, False)
                self.names[phase] = name
                return name
            token = f"{index:02d}"
            self._drop_phase_temporaries(token)
            temporary = self._temporary_name(token)
            started = time.perf_counter()
            try:
                if previous is None:
                    self._create_database(temporary, "template0")
                    self._build_first(temporary, seed_function)
                else:
                    # Published templates have ALLOW_CONNECTIONS=false and are
                    # never opened by tests, so no connection toggle or wait is
                    # needed before cloning them.
                    self._create_database(temporary, previous)
                    self._extend(temporary, seed_function)
                self._set_allow_connections(temporary, False)
                self._rename_database(temporary, name)
                self.template_build_metrics.append(
                    {
                        "phase": phase,
                        "database": name,
                        "seconds": time.perf_counter() - started,
                    }
                )
            except BaseException:
                self._drop_database_best_effort(temporary, "failed template build")
                raise
        self.names[phase] = name
        return name

    def get_model_l2(self) -> str:
        key = "model_l2"
        if key in self.names:
            return self.names[key]

        name = f"pub_seed_{self.fingerprint}_{key}"
        if self._database_exists(name):
            # Cached lookups also ALTER pg_database; serialize that catalog row.
            with self._template_lock(key):
                if self._database_exists(name):
                    self._set_allow_connections(name, False)
                    self.names[key] = name
                    return name

        with self._template_lock(key):
            if self._database_exists(name):
                self._set_allow_connections(name, False)
                self.names[key] = name
                return name
            token = "ml"
            self._drop_phase_temporaries(token)
            temporary = self._temporary_name(token)
            started = time.perf_counter()
            try:
                self._create_database(temporary, "template0")
                engine = create_engine(_postgres_database_url(self.admin_url, temporary))
                try:
                    _build_model_l2(engine)
                finally:
                    engine.dispose()
                self._set_allow_connections(temporary, False)
                self._rename_database(temporary, name)
                self.template_build_metrics.append(
                    {
                        "phase": key,
                        "database": name,
                        "seconds": time.perf_counter() - started,
                    }
                )
            except BaseException:
                self._drop_database_best_effort(temporary, "failed template build")
                raise
        self.names[key] = name
        return name

    @contextmanager
    def session(self, phase: str) -> Iterator[Session]:
        template = self.get(phase)
        with self._session(self._worker_database(phase, template)) as session:
            yield session

    @contextmanager
    def model_l2_session(self) -> Iterator[Session]:
        template = self.get_model_l2()
        with self._session(self._worker_database("model_l2", template)) as session:
            yield session

    @contextmanager
    def _session(self, name: str) -> Iterator[Session]:
        # A worker database belongs to this process for its whole session.  It
        # remains connectable, so nested fixtures need no ALLOW_CONNECTIONS
        # bookkeeping; rollback still isolates every fixture invocation.
        engine = create_engine(_postgres_database_url(self.admin_url, name))
        connection = None
        transaction = None
        session = None
        try:
            connection = engine.connect()
            transaction = connection.begin()
            session = Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            )
            yield session
        finally:
            if session is not None:
                session.close()
            if transaction is not None and transaction.is_active:
                transaction.rollback()
            if connection is not None:
                connection.close()
            engine.dispose()

    def _worker_database(self, phase: str, template: str) -> str:
        if phase in self.worker_names:
            return self.worker_names[phase]
        name = _postgres_worker_database_name(
            self.fingerprint, self.run_id, self.worker_id, phase
        )
        if self._database_exists(name):
            self._drop_database(name)
        started = time.perf_counter()
        self._create_database(name, template)
        self.clone_metrics.append(
            {
                "phase": phase,
                "database": name,
                "seconds": time.perf_counter() - started,
            }
        )
        self.worker_names[phase] = name
        return name

    def _write_clone_metrics(self) -> None:
        metrics_root = os.environ.get(_POSTGRES_METRICS_DIR_ENV)
        if not metrics_root:
            return
        root = Path(metrics_root)
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprint": self.fingerprint,
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "pid": os.getpid(),
            "copy_count": len(self.clone_metrics),
            "copy_seconds": sum(
                float(item["seconds"]) for item in self.clone_metrics
            ),
            "copies": self.clone_metrics,
            "template_build_count": len(self.template_build_metrics),
            "template_build_seconds": sum(
                float(item["seconds"]) for item in self.template_build_metrics
            ),
            "template_builds": self.template_build_metrics,
        }
        destination = root / f"{self.run_id}-{self.worker_id}-{os.getpid()}.json"
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _database_exists(self, name: str) -> bool:
        with self.admin_engine.connect() as connection:
            return bool(
                connection.exec_driver_sql(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (name,),
                ).scalar()
            )

    def _drop_stale_generations(self) -> None:
        with self.admin_engine.connect() as connection:
            names = list(
                connection.exec_driver_sql(
                    "SELECT datname FROM pg_database "
                    "WHERE datname LIKE %s ESCAPE '\\'",
                    ("pub\\_seed\\_%",),
                ).scalars()
            )
        for name in names:
            match = _POSTGRES_SNAPSHOT_NAME.fullmatch(name)
            if match is not None and match.group(1) != self.fingerprint:
                blockers = self._database_blockers(name)
                if blockers:
                    warnings.warn(
                        f"leaving stale PostgreSQL template {name!r} because it "
                        "still has blockers(pid, role, application_name)="
                        f"{blockers}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                else:
                    self._drop_database_best_effort(
                        name, "stale template generation"
                    )

        with self.admin_engine.connect() as connection:
            transient_names = list(
                connection.exec_driver_sql(
                    "SELECT datname FROM pg_database "
                    "WHERE datname LIKE %s ESCAPE '\\' OR datname LIKE %s ESCAPE '\\'",
                    ("pub\\_tw\\_%", "pub\\_seed\\_tmp\\_%"),
                ).scalars()
            )
        grouped: dict[str, list[str]] = {}
        for name in transient_names:
            match = _POSTGRES_WORKER_NAME.fullmatch(name)
            if match is None:
                match = _POSTGRES_TEMP_NAME.fullmatch(name)
            if match is None:
                warnings.warn(
                    f"leaving unrecognized PostgreSQL test database {name!r}; "
                    "its owning run cannot be proven dead",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            run_id = match.group(2)
            if run_id != self.run_id:
                grouped.setdefault(run_id, []).append(name)
        for run_id, run_names in grouped.items():
            with self._dead_run_cleanup_lock(run_id) as can_clean:
                if not can_clean:
                    continue
                for name in run_names:
                    self._drop_database_best_effort(name, f"orphaned run {run_id}")

    @contextmanager
    def _dead_run_cleanup_lock(self, run_id: str) -> Iterator[bool]:
        key = _postgres_advisory_key("run", run_id)
        connection = self.admin_engine.connect()
        acquired = bool(
            connection.exec_driver_sql(
                "SELECT pg_try_advisory_lock(%s)", (key,)
            ).scalar_one()
        )
        try:
            # Every live worker holds the shared form of this lock.  Therefore
            # an exclusive try-lock succeeds only after the entire run died.
            yield acquired
        finally:
            if acquired:
                connection.exec_driver_sql(
                    "SELECT pg_advisory_unlock(%s)", (key,)
                )
            connection.close()

    @contextmanager
    def _template_lock(self, phase: str) -> Iterator[None]:
        key = _postgres_advisory_key(self.fingerprint, phase)
        connection = self.admin_engine.connect()
        deadline = time.monotonic() + _POSTGRES_TEMPLATE_LOCK_TIMEOUT_SECONDS
        while not bool(
            connection.exec_driver_sql(
                "SELECT pg_try_advisory_lock(%s)", (key,)
            ).scalar_one()
        ):
            if time.monotonic() >= deadline:
                holders = self._advisory_lock_holders(key)
                connection.close()
                raise RuntimeError(
                    "timed out after "
                    f"{_POSTGRES_TEMPLATE_LOCK_TIMEOUT_SECONDS}s waiting for "
                    f"PostgreSQL seed phase {phase!r}; waiter run={self.run_id} "
                    f"worker={self.worker_id} pid={os.getpid()}; holders={holders}"
                )
            time.sleep(0.1)
        try:
            yield
        finally:
            connection.exec_driver_sql(
                "SELECT pg_advisory_unlock(%s)", (key,)
            )
            connection.close()

    def _advisory_lock_holders(self, key: int) -> list[tuple[object, ...]]:
        with self.admin_engine.connect() as connection:
            return list(
                connection.exec_driver_sql(
                    "SELECT a.pid, a.usename, a.application_name "
                    "FROM pg_locks l LEFT JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE l.locktype = 'advisory' AND l.granted "
                    "AND ((l.classid::bigint << 32) | l.objid::bigint) = %s",
                    (key,),
                ).all()
            )

    def _temporary_name(self, token: str) -> str:
        return (
            f"pub_seed_tmp_{self.fingerprint[:8]}_{self.run_id}_{token}_"
            f"{uuid.uuid4().hex[:6]}"
        )

    def _drop_phase_temporaries(self, token: str) -> None:
        with self.admin_engine.connect() as connection:
            names = list(
                connection.exec_driver_sql(
                    "SELECT datname FROM pg_database",
                ).scalars()
            )
        for name in names:
            match = _POSTGRES_TEMP_NAME.fullmatch(name)
            if (
                match is None
                or match.group(1) != self.fingerprint[:8]
                or match.group(3) != token
            ):
                continue
            self._drop_database_best_effort(name, f"stale phase {token} build")

    def _create_database(self, name: str, template: str) -> None:
        statement = (
            f"CREATE DATABASE {_quote_postgres_database(name)} "
            f"TEMPLATE {_quote_postgres_database(template)} STRATEGY = file_copy"
        )
        with self.admin_engine.connect() as connection:
            connection.exec_driver_sql(statement)

    def _drop_database(self, name: str) -> None:
        if not self._database_exists(name):
            return
        with self.admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE {_quote_postgres_database(name)} WITH (FORCE)"
            )

    def _drop_database_best_effort(self, name: str, purpose: str) -> None:
        try:
            self._drop_database(name)
        except BaseException as error:
            if isinstance(error, InvalidCatalogName) or isinstance(
                getattr(error, "orig", None), InvalidCatalogName
            ):
                return
            blockers = self._database_blockers(name)
            warnings.warn(
                f"could not drop PostgreSQL database {name!r} during {purpose}: "
                f"{error!r}; blockers(pid, role, application_name)={blockers}",
                RuntimeWarning,
                stacklevel=2,
            )

    def _database_blockers(self, name: str) -> list[tuple[object, ...]]:
        try:
            with self.admin_engine.connect() as connection:
                return list(
                    connection.exec_driver_sql(
                        "SELECT pid, usename, application_name "
                        "FROM pg_stat_activity WHERE datname = %s ORDER BY pid",
                        (name,),
                    ).all()
                )
        except BaseException as error:
            return [("unavailable", type(error).__name__, str(error))]

    def _set_allow_connections(self, name: str, allow: bool) -> None:
        value = "true" if allow else "false"
        with self.admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"ALTER DATABASE {_quote_postgres_database(name)} "
                f"WITH ALLOW_CONNECTIONS {value}"
            )

    def _rename_database(self, source: str, destination: str) -> None:
        with self.admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"ALTER DATABASE {_quote_postgres_database(source)} "
                f"RENAME TO {_quote_postgres_database(destination)}"
            )

    def _build_first(self, name: str, seed_function: SeedFunction) -> None:
        database_url = _postgres_database_url(self.admin_url, name)
        engine = create_engine(database_url)
        try:
            _upgrade_schema(database_url)
            with Session(engine) as session:
                seed_language(session)
                seed_inference_rules(session)
                seed_function(session)
                session.commit()
        finally:
            engine.dispose()

    def _extend(self, name: str, seed_function: SeedFunction) -> None:
        engine = create_engine(_postgres_database_url(self.admin_url, name))
        try:
            with Session(engine) as session:
                seed_function(session)
                session.commit()
        finally:
            engine.dispose()


@dataclass
class SeedSnapshotFactory:
    sqlite: SQLiteSeedSnapshotFactory
    postgresql: PostgreSQLSeedSnapshotFactory | None

    @contextmanager
    def session(self, phase: str, database: str) -> Iterator[Session]:
        if database == "sqlite":
            with self.sqlite.session(phase) as session:
                yield session
            return
        if database == "postgresql" and self.postgresql is not None:
            with self.postgresql.session(phase) as session:
                yield session
            return
        raise RuntimeError(f"test database {database!r} is not configured")

    @contextmanager
    def l2_origin_urls(self, database: str) -> Iterator[tuple[str, str]]:
        """Yield URLs for the Alembic-origin and create_all-origin public databases.

        PostgreSQL URLs point at this worker's writable clones.  Cached template
        databases remain non-connectable even for the content comparison.
        """
        if database == "sqlite":
            with self.sqlite.session("public_demo") as a, self.sqlite.model_l2_session() as b:
                urls = (_session_database_url(a), _session_database_url(b))
                _populate_public_guard_origins(urls)
                yield urls
        elif database == "postgresql" and self.postgresql is not None:
            factory = self.postgresql
            first = factory._worker_database("guard_a_" + uuid.uuid4().hex[:8], factory.get("public_demo"))
            second = factory._worker_database("guard_b_" + uuid.uuid4().hex[:8], factory.get_model_l2())
            urls = tuple(factory.admin_url.set(database=name).render_as_string(hide_password=False) for name in (first, second))
            _populate_public_guard_origins(urls)
            yield urls
        else:
            raise RuntimeError("Unsupported public guard database")

    def close(self) -> None:
        if self.postgresql is not None:
            self.postgresql.close()


def _copy_snapshot(snapshot: Path) -> tuple[Engine, Session, Path]:
    """Open an isolated writable copy without replaying SQLite pages in Python."""
    descriptor, name = tempfile.mkstemp(prefix="dem-seed-session-", suffix=".db")
    os.close(descriptor)
    path = Path(name)
    shutil.copy2(snapshot, path)
    engine = _file_engine(path)
    return engine, Session(engine), path


def _session_database_url(session: Session) -> str:
    bind = session.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    return engine.url.render_as_string(hide_password=False)


def _close_snapshot_copy(engine: Engine, session: Session, path: Path) -> None:
    session.close()
    engine.dispose()
    path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def seed_snapshot_factory(
    pytestconfig: pytest.Config,
) -> Iterator[SeedSnapshotFactory]:
    cache_root = pytestconfig.cache.mkdir("dem-public-seed-snapshots")
    fingerprint = _snapshot_cache_fingerprint()
    root = cache_root / fingerprint
    root.mkdir(exist_ok=True)
    for stale in cache_root.iterdir():
        if stale.is_dir() and stale != root:
            shutil.rmtree(stale, ignore_errors=True)

    configured_database = os.environ.get(_TEST_DATABASE_ENV, "sqlite").lower()
    if configured_database not in {"sqlite", "postgresql"}:
        raise pytest.UsageError(
            f"{_TEST_DATABASE_ENV} must be 'sqlite' or 'postgresql', "
            f"not {configured_database!r}"
        )
    factory = SeedSnapshotFactory(
        sqlite=SQLiteSeedSnapshotFactory(root),
        postgresql=(
            PostgreSQLSeedSnapshotFactory(fingerprint)
            if configured_database == "postgresql"
            else None
        ),
    )
    try:
        yield factory
    finally:
        factory.close()


def _snapshot_fingerprint() -> str:
    """Mirror the workspace-template content fingerprint."""
    repository = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    digest.update(_SNAPSHOT_CACHE_VERSION.encode())
    digest.update(sys.version.encode())
    digest.update(sqlalchemy.__version__.encode())
    paths = [
        *sorted((repository / "dem").rglob("*.py")),
        *sorted((repository / "demlang").rglob("*.py")),
        repository / "pyproject.toml",
    ]
    for path in paths:
        digest.update(path.relative_to(repository).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def _snapshot_cache_fingerprint() -> str:
    """Invalidate Alembic-origin snapshots when migration inputs change."""
    repository = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    digest.update(_snapshot_fingerprint().encode())
    digest.update(version("alembic").encode())
    paths = [
        repository / "alembic.ini",
        *sorted((repository / "alembic").rglob("*.py")),
    ]
    for path in paths:
        digest.update(path.relative_to(repository).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:20]


def _phase_for(request: pytest.FixtureRequest) -> str:
    phase = getattr(request.module, "SEED_PHASE", "public_core")
    if phase is None:
        raise RuntimeError("module using a seed snapshot must define SEED_PHASE")
    return phase


def _database_for(request: pytest.FixtureRequest) -> str:
    database = getattr(request.module, "SEED_DATABASE", None)
    if database is None:
        database = os.environ.get(_TEST_DATABASE_ENV, "sqlite")
    database = database.lower()
    if database not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"unknown test database: {database!r}")
    return database


@pytest.fixture(scope="module")
def seeded_session(
    request: pytest.FixtureRequest,
    seed_snapshot_factory: SeedSnapshotFactory,
) -> Iterator[Session]:
    with seed_snapshot_factory.session(
        _phase_for(request), _database_for(request)
    ) as session:
        yield session


@pytest.fixture
def fresh_seeded_session(
    request: pytest.FixtureRequest,
    seed_snapshot_factory: SeedSnapshotFactory,
) -> Iterator[Session]:
    with seed_snapshot_factory.session(
        _phase_for(request), _database_for(request)
    ) as session:
        yield session


@pytest.fixture(scope="module")
def all_seeded_session(
    request: pytest.FixtureRequest,
    seed_snapshot_factory: SeedSnapshotFactory,
) -> Iterator[Session]:
    with seed_snapshot_factory.session(
        "public_demo", _database_for(request)
    ) as session:
        yield session


@pytest.fixture(scope="module")
def l2_seeded_session(
    request: pytest.FixtureRequest,
    seed_snapshot_factory: SeedSnapshotFactory,
) -> Iterator[Session]:
    with seed_snapshot_factory.session("public_demo", _database_for(request)) as session:
        yield session


@pytest.fixture
def expansion_check() -> Callable[[Session, Iterable[str]], int]:
    """Validate raw rules and replay the admissible-rule expansion."""

    def check(session: Session, theorem_names: Iterable[str]) -> int:
        from dem.db.seeds.hilbert_toolkit import HilbertToolkit, ProofStepSpec
        from dem.services.proof import RAW_INFERENCE_RULE_KINDS, ProofService
        from dem.services.theorem import TheoremService

        toolkit = HilbertToolkit(session)
        proofs = ProofService(session)
        theorems = TheoremService(session)

        names = list(theorem_names)
        hardest: tuple[int, int, str, int] | None = None
        smallest: tuple[int, str, int] | None = None
        for name in names:
            theorem = theorems.get_by_name(name)
            proof = next(
                item
                for item in proofs.list_for_theorem(theorem.id)
                if item.status == "verified"
            )
            steps = proofs.list_steps(proof.id)
            intro_count = 0
            for step in steps:
                rule = step.inference_rule
                assert rule is None or rule.kind in RAW_INFERENCE_RULE_KINDS, (
                    name,
                    rule.kind if rule else None,
                )
                if rule is not None and rule.kind == "implication_intro":
                    intro_count += 1
            if intro_count == 0:
                continue
            candidate = (intro_count, -len(steps), name, proof.id)
            if hardest is None or candidate > hardest:
                hardest = candidate
            small = (len(steps), name, proof.id)
            if smallest is None or small < smallest:
                smallest = small

        def expand(proof_id: int) -> tuple[list[ProofStepSpec], list[object]]:
            specs = [
                ProofStepSpec(step_input, tokens)
                for step_input, tokens in proofs.reconstruct_steps(proof_id)
            ]
            expanded = toolkit.expand_implication_intro(
                toolkit.from_proof_step_specs(specs)
            )
            assert {step.kind for step in expanded} & {
                "assumption",
                "imp_intro",
            } == set()
            assert expanded[-1].tokens == specs[-1].conclusion_tokens
            return specs, expanded

        if hardest is not None:
            expand(hardest[3])

        if smallest is not None:
            _, name, proof_id = smallest
            theorem = theorems.get_by_name(name)
            specs, expanded = expand(proof_id)
            replay = toolkit._prove(
                toolkit._get_or_create_theorem(
                    f"expansion_check_{name}",
                    specs[-1].conclusion_tokens,
                    [
                        proofs._tokens_for_formula(formula.id)
                        for _, formula in theorems.list_premises(theorem.id)
                    ],
                ),
                toolkit.to_proof_step_specs(expanded),
            )
            assert replay.status == "verified", name

        return len(names)

    return check


def _add_schema_fixture_proofs(session: Session) -> None:
    """Add five genuinely verified A-only proofs for trigger matrices."""
    from dem.services.axiom import AxiomService
    from dem.services.symbol import SymbolService
    from dem.services.formula import FormulaService
    from dem.services.theorem import TheoremService
    from dem.services.proof import ProofService
    from dem.types import Token, AxiomStepInput, PremiseStepInput, Substitution, PropSubst, TermSubst, TheoremStepInput

    axioms = AxiomService(session)
    formulas = FormulaService(session)
    symbols = SymbolService(session)
    theorems = TheoremService(session)
    proofs = ProofService(session)
    for axiom_name in ("hilbert_k", "hilbert_s"):
        axiom = axioms.get_by_name(axiom_name)
        theorem = theorems.register(f"schema_fixture_{axiom_name}", axiom.formula_id)
        proof = proofs.create_proof(theorem.id)
        proofs.add_step(proof.id, AxiomStepInput(axiom.id), axiom.formula_id)
        proofs.validate(proof.id)
    premise_formula = axioms.get_by_name("hilbert_k").formula_id
    premise_theorem = theorems.register(
        "schema_fixture_premise", premise_formula, [premise_formula]
    )
    premise_proof = proofs.create_proof(premise_theorem.id)
    proofs.add_step(premise_proof.id, PremiseStepInput(0), premise_formula)
    proofs.validate(premise_proof.id)

    phi1 = symbols.get_by_name("φ¹")
    t = symbols.get_by_name("t")
    x = symbols.get_by_name("x")
    equality = symbols.get_by_role("equality")
    schema = formulas.register(
        [Token(symbol_id=equality.id), Token(symbol_id=x.id), Token(symbol_id=x.id)]
    )
    x_formula = formulas.register([Token(symbol_id=x.id)])
    forall_elim = axioms.get_by_name("hilbert_forall_elim")
    substitution = Substitution(
        term_substs=(TermSubst(t.id, x_formula.id),),
        prop_substs=(PropSubst(phi1.id, schema.id, (x.id,)),),
    )
    instantiated = formulas.register(
        proofs.compute_substituted_tokens(forall_elim.formula_id, substitution)
    )
    substitution_theorem = theorems.register(
        "schema_fixture_substitution", instantiated.id
    )
    substitution_proof = proofs.create_proof(substitution_theorem.id)
    proofs.add_step(
        substitution_proof.id,
        AxiomStepInput(forall_elim.id, substitution),
        instantiated.id,
    )
    proofs.validate(substitution_proof.id)

    applied_theorem = theorems.register(
        "schema_fixture_applied", premise_formula, [premise_formula]
    )
    applied_proof = proofs.create_proof(applied_theorem.id)
    proofs.add_step(applied_proof.id, PremiseStepInput(0), premise_formula)
    proofs.add_step(
        applied_proof.id,
        TheoremStepInput(premise_proof.id, Substitution(), (0,)),
        premise_formula,
    )
    proofs.validate(applied_proof.id)


def _populate_public_guard_origins(urls):
    for url in urls:
        engine = create_engine(url)
        try:
            with Session(engine) as session, session.begin():
                _add_schema_fixture_proofs(session)
        finally:
            engine.dispose()
