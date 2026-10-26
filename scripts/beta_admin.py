"""Offline PostgreSQL beta operations. No database-name arguments or API control."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url, URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from dem.db.models import Base
from scripts import beta_base

UTC = timezone.utc
COMMIT = r"(?:[0-9a-f]{40}|[0-9a-f]{64})"
BACKUP = re.compile(r"dem-beta-(backup|preswap)-\d{8}T\d{12}Z-[0-9a-f]{8}\.dump\Z")


class AdminError(ValueError):
    """Messages are safe public diagnostics, never driver messages."""


@dataclass(frozen=True)
class Names:
    prefix: str = "dem_beta"

    def __post_init__(self):
        if self.prefix != "dem_beta" and not re.fullmatch(r"dem_beta_test_[0-9a-f]{12}", self.prefix):
            raise AdminError("invalid database namespace")

    def name(self, suffix):
        if suffix not in ("base", "base_next", "base_old", "live", "live_next", "live_old"):
            raise AdminError("database is outside the allowlist")
        return self.prefix + "_" + suffix

    @property
    def allowed(self):
        return {self.name(suffix) for suffix in ("base", "base_next", "base_old", "live", "live_next", "live_old")}


def next_reset(now, schedule):
    match = re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ([0-2]\d):([0-5]\d) (\S+)", schedule)
    if not match or int(match[2]) > 23:
        raise AdminError("schedule must be 'Mon 04:00 Asia/Tokyo'")
    try:
        zone = ZoneInfo(match[4])
    except (KeyError, ValueError):
        raise AdminError("unknown schedule timezone") from None
    local = now.astimezone(zone)
    target = local.replace(hour=int(match[2]), minute=int(match[3]), second=0, microsecond=0, fold=0)
    target += timedelta(days=(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun").index(match[1]) - local.weekday()) % 7)
    if target.astimezone(UTC) <= now.astimezone(UTC):
        target += timedelta(days=7)
    # Reject nonexistent DST wall times; choose fold=0 for ambiguous times.
    if target.astimezone(UTC).astimezone(zone).replace(fold=0) != target.replace(fold=0):
        raise AdminError("next scheduled wall time does not exist")
    return target.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class Settings:
    admin_url: str = field(repr=False)
    flag_dir: Path
    status_file: Path
    backup_dir: Path
    state_dir: Path
    commit: str
    pg_bin: Path
    owner: str = "dem_beta_owner"
    app: str = "dem_beta_app"
    owner_password: str | None = field(default=None, repr=False)
    app_password: str | None = field(default=None, repr=False)
    schedule: str = "Mon 04:00 Asia/Tokyo"
    names: Names = field(default_factory=Names)

    @classmethod
    def from_env(cls):
        required = ("DEM_BETA_ADMIN_DATABASE_URL", "DEM_BETA_FLAG_DIR", "DEM_BETA_STATUS_FILE", "DEM_BETA_BACKUP_DIR")
        if any(not os.environ.get(name) for name in required):
            raise AdminError("missing beta administration environment settings")
        commit = os.environ.get("DEM_BETA_COMMIT")
        if not commit:
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            commit = result.stdout.strip() if result.returncode == 0 else ""
        binary = os.environ.get("DEM_BETA_PG_BIN")
        if not binary:
            found = shutil.which("pg_dump")
            binary = str(Path(found).parent) if found else "C:/Program Files/PostgreSQL/18/bin"
        status = Path(os.environ["DEM_BETA_STATUS_FILE"])
        return cls(os.environ[required[0]], Path(os.environ[required[1]]), status, Path(os.environ[required[3]]),
                   Path(os.environ.get("DEM_BETA_STATE_DIR", str(status.parent / "beta-admin"))), commit, Path(binary),
                   owner_password=os.environ.get("DEM_BETA_OWNER_PASSWORD"), app_password=os.environ.get("DEM_BETA_APP_PASSWORD"),
                   schedule=os.environ.get("DEM_BETA_RESET_SCHEDULE", "Mon 04:00 Asia/Tokyo"))


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class BetaAdmin:
    def __init__(self, settings, *, builder=None, permission_probe=None, hook=None):
        self.settings = settings
        self.names = settings.names
        url = make_url(settings.admin_url)
        if url.get_backend_name() != "postgresql" or url.database != "postgres":
            raise AdminError("administration URL must connect to the postgres control database")
        if set(url.query) - {"sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout", "application_name"}:
            raise AdminError("administration URL contains unsupported connection overrides")
        if not re.fullmatch(COMMIT, settings.commit):
            raise AdminError("a full deployment commit is required")
        next_reset(datetime.now(UTC), settings.schedule)
        self.url = url
        self.engine = create_engine(url, poolclass=NullPool, hide_parameters=True)
        self.builder = builder or self._production_build
        self.permission_probe = permission_probe or self._probe_permissions
        self.hook = hook or (lambda stage: None)
        self.control = None

    def close(self):
        self.engine.dispose()

    def _quote(self, name):
        return self.engine.dialect.identifier_preparer.quote(name)

    def _database(self, name):
        if name not in self.names.allowed:
            raise AdminError("database is outside the allowlist")
        return self._quote(name)

    def _info(self, name):
        self._database(name)
        row = self.control.execute(text("""SELECT oid, datname, datallowconn, pg_get_userbyid(datdba) AS owner,
            shobj_description(oid,'pg_database') AS marker FROM pg_database WHERE datname=:name"""), {"name": name}).mappings().first()
        return dict(row) if row else None

    def _marker(self, name, row=None):
        row = row or self._info(name)
        if row is None:
            raise AdminError("required beta database is missing")
        kind = "base" if name.startswith(self.names.prefix + "_base") else "live"
        pattern = rf"dem-beta:{kind}:({COMMIT})" + (r":(.+)" if kind == "live" else "")
        match = re.fullmatch(pattern, row["marker"] or "")
        if not match or row["owner"] != self.settings.owner:
            raise AdminError("database marker or owner mismatch; no destructive action allowed")
        if kind == "live":
            try:
                stamp = datetime.fromisoformat(match[2])
                if stamp.utcoffset() != timedelta(0):
                    raise ValueError()
            except ValueError:
                raise AdminError("invalid live creation timestamp") from None
        return match[1]

    def _require(self, name):
        row = self._info(name)
        self._marker(name, row)
        return row

    def _comment(self, name, marker):
        # psycopg's Literal quotes values without ever logging them.
        from psycopg.sql import Literal
        self.control.exec_driver_sql(f"COMMENT ON DATABASE {self._database(name)} IS {Literal(marker).as_string()}")

    def _allow(self, name, enabled):
        self._require(name)
        self.control.exec_driver_sql(f"ALTER DATABASE {self._database(name)} ALLOW_CONNECTIONS {'true' if enabled else 'false'}")

    def _drop(self, name):
        if self._info(name) is not None:
            self._require(name)
            self.control.exec_driver_sql(f"DROP DATABASE {self._database(name)}")

    def _rename_pair(self, current, incoming, old):
        self._require(incoming)
        present = self._info(current) is not None
        if present:
            self._require(current)
        if self._info(old):
            raise AdminError("old database requires recovery before another swap")
        with self.engine.begin() as connection:
            if present:
                connection.exec_driver_sql(f"ALTER DATABASE {self._database(current)} RENAME TO {self._database(old)}")
            self.hook("after_first_rename")
            connection.exec_driver_sql(f"ALTER DATABASE {self._database(incoming)} RENAME TO {self._database(current)}")
        return present

    def _rollback_pair(self, current, incoming, old, had_old):
        self._require(current)
        if had_old:
            self._require(old)
        with self.engine.begin() as connection:
            connection.exec_driver_sql(f"ALTER DATABASE {self._database(current)} RENAME TO {self._database(incoming)}")
            if had_old:
                connection.exec_driver_sql(f"ALTER DATABASE {self._database(old)} RENAME TO {self._database(current)}")

    def _data_engine(self, name, *, app=False):
        self._require(name)
        url = URL.create(self.url.drivername, username=self.settings.app if app else self.settings.owner,
            password=self.settings.app_password if app else self.settings.owner_password,
            host=self.url.host, port=self.url.port, database=name, query=self.url.query)
        return create_engine(url, poolclass=NullPool, hide_parameters=True)

    def _versions(self):
        server = int(self.control.scalar(text("SHOW server_version_num"))) // 10000
        for utility in ("pg_dump", "pg_restore"):
            completed = subprocess.run([str(self._binary(utility)), "--version"], capture_output=True, text=True, timeout=20)
            match = re.search(r"PostgreSQL\) (\d+)\.", completed.stdout)
            if completed.returncode or not match or int(match[1]) != server or server != 18:
                raise AdminError("PostgreSQL server and dump/restore must all be major version 18")

    def _binary(self, utility):
        path = self.settings.pg_bin / (utility + (".exe" if os.name == "nt" else ""))
        if not path.is_file():
            raise AdminError("PostgreSQL dump/restore binary missing")
        return path

    @contextmanager
    def _operation(self):
        if os.environ.get("DEM_BETA") != "1":
            raise AdminError("DEM_BETA=1 is required; nothing changed")
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            self.control = connection
            key = int.from_bytes(hashlib.sha256(self.names.prefix.encode()).digest()[:8], "big", signed=True)
            locked = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            if not locked:
                raise AdminError("another beta administration operation is running")
            try:
                # Check every occupied allowlisted name before filesystem or DB writes.
                for name in sorted(self.names.allowed):
                    row = self._info(name)
                    if row:
                        self._marker(name, row)
                self._versions()
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                self.control = None

    def execute(self, command, *, file=None):
        actions = {"roles": self._roles, "build-base": self._build_base,
                   "reset prepare": self._prepare, "reset swap": self._swap, "reset finish": self._finish,
                   "backup": self._backup, "restore": lambda: self._restore(file), "status": self._status}
        if command not in actions:
            raise AdminError("unknown beta administration operation")
        with self._operation():
            return actions[command]()

    def _create(self, name, marker, template=None):
        if self._info(name):
            self._drop(name)
        template_sql = self._database(template) if template else "template0"
        if template:
            self._require(template)
        self.control.exec_driver_sql(f"CREATE DATABASE {self._database(name)} OWNER {self._quote(self.settings.owner)} TEMPLATE {template_sql}")
        # A failure before this COMMENT leaves an unmarked DB; never delete it
        # by guessing ownership on a later invocation.
        self._comment(name, marker)

    def _roles(self):
        from psycopg.sql import Literal
        for name, password in ((self.settings.owner, self.settings.owner_password), (self.settings.app, self.settings.app_password)):
            if not password:
                raise AdminError("owner and API role passwords must be supplied in environment variables")
            row = self.control.execute(text("SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=:role"), {"role": name}).first()
            if row is None:
                self.control.exec_driver_sql(f"CREATE ROLE {self._quote(name)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {Literal(password).as_string()}")
            elif tuple(row) != (True, False, False, False, False, False):
                raise AdminError("existing beta role has unexpected attributes")
            if self.control.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:role)"), {"role": name}):
                raise AdminError("beta roles must not inherit other roles")
        app = self._quote(self.settings.app)
        self.control.exec_driver_sql(f"ALTER ROLE {app} SET statement_timeout = '10s'")
        self.control.exec_driver_sql(f"ALTER ROLE {app} SET idle_in_transaction_session_timeout = '30s'")
        administrator = self.control.scalar(text("SELECT current_user"))
        if administrator != self.settings.owner:
            for option in ("INHERIT", "SET"):
                self.control.exec_driver_sql(f"GRANT {self._quote(self.settings.owner)} TO {self._quote(administrator)} WITH {option} TRUE")
        if self._info(self.names.name("live")):
            self._grant(self.names.name("live"))
        return {"ok": True, "roles": [self.settings.owner, self.settings.app]}

    def _grant(self, name):
        self._require(name)
        database, app = self._database(name), self._quote(self.settings.app)
        engine = self._data_engine(name)
        try:
            with engine.begin() as connection:
                for sql in (f"REVOKE ALL ON DATABASE {database} FROM PUBLIC", f"REVOKE ALL ON DATABASE {database} FROM {app}",
                            f"GRANT CONNECT ON DATABASE {database} TO {app}",
                            "REVOKE ALL ON SCHEMA public FROM PUBLIC", f"REVOKE ALL ON SCHEMA public FROM {app}",
                            f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app}",
                            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {app}", f"GRANT USAGE ON SCHEMA public TO {app}",
                            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {app}",
                            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {app}",
                            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app}",
                            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {app}"):
                    connection.exec_driver_sql(sql)
        finally:
            engine.dispose()

    def _probe_permissions(self, name):
        if self.settings.app == self.settings.owner:
            raise AdminError("API role must differ from owner")
        engine = self._data_engine(name, app=True)
        forbidden = ("ALTER TABLE public.symbol DISABLE TRIGGER ALL", "CREATE TABLE public.beta_permission_probe(id integer)",
                     "DROP TRIGGER published_symbol_update ON public.symbol", "ALTER TABLE public.symbol ADD COLUMN beta_permission_probe integer",
                     "TRUNCATE TABLE public.symbol")
        try:
            with engine.connect() as connection:
                if connection.scalar(text("SELECT current_user")) != self.settings.app:
                    raise AdminError("permission probe did not connect as API role")
                connection.execute(text("SELECT id FROM public.symbol LIMIT 1"))
                connection.rollback()
                for statement in forbidden:
                    try:
                        with connection.begin():
                            connection.exec_driver_sql(statement)
                            raise AdminError("API role unexpectedly accepted forbidden DDL or TRUNCATE")
                    except DBAPIError as exc:
                        if getattr(exc.orig, "sqlstate", None) != "42501":
                            raise AdminError("permission probe failed for a reason other than denied privilege") from None
                try:
                    with connection.begin():
                        result = connection.exec_driver_sql("UPDATE public.symbol SET latex_template='beta-permission-probe' WHERE id=(SELECT MIN(s.id) FROM public.symbol s JOIN public.package_release r ON r.id=s.release_id WHERE r.published_at IS NOT NULL)")
                        raise AdminError("API role unexpectedly modified frozen content")
                except DBAPIError as exc:
                    if getattr(exc.orig, "sqlstate", None) != "23514" or "published" not in str(exc.orig):
                        raise AdminError("frozen-row probe was not rejected by the published guard") from None
        finally:
            engine.dispose()
        return {"ok": True}

    def _inspect_content(self, name, *, live=False):
        self._require(name)
        reference = self._reference() if live else None
        engine = self._data_engine(name)
        try:
            result = beta_base.verify(engine, live_releases=reference["releases"] if live else None)
            if not result["ok"]:
                raise AdminError("database verification failed; reset from base if restore cannot be verified")
            with beta_base.readonly_session(engine) as session:
                releases = beta_base.release_snapshot(session, result["checks"]["digests"]["actual"])
                counts = {name: session.scalar(select(func.count()).select_from(Base.metadata.tables[name])) for name in ("formula", "theorem", "proof_step")}
                size = session.scalar(text("SELECT pg_database_size(current_database())"))
            permissions = self.permission_probe(name)
            if permissions.get("ok") is not True:
                raise AdminError("API permission verification failed")
            return {"verification": result, "releases": releases, "counts": counts, "bytes": size}
        finally:
            engine.dispose()

    @property
    def _reference_path(self):
        return self.settings.state_dir / "base.json"

    @property
    def _prepared_path(self):
        return self.settings.state_dir / "prepared.json"

    @property
    def _flag(self):
        return self.settings.flag_dir / "read_only"

    def _json(self, path, value):
        atomic_write(path, json.dumps(value, sort_keys=True).encode())

    def _reference(self):
        base = self._require(self.names.name("base"))
        reference = json.loads(self._reference_path.read_text(encoding="utf-8"))
        if reference["oid"] != base["oid"] or reference["marker"] != base["marker"] or base["datallowconn"]:
            raise AdminError("sealed base reference does not match the template")
        return reference

    def _production_build(self, name):
        engine = self._data_engine(name)
        try:
            result = beta_base.build(engine.url.render_as_string(hide_password=False))
            if not result["ok"]:
                raise AdminError("base build did not pass verification")
        finally:
            engine.dispose()

    def _restore_file(self, path, previous):
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, previous)

    def _build_base(self):
        if self._prepared_path.exists():
            raise AdminError("finish or recover the prepared live operation before rebuilding base")
        current, incoming, old = (self.names.name(s) for s in ("base", "base_next", "base_old"))
        if self._info(old):
            raise AdminError("old base requires recovery")
        previous = self._reference_path.read_bytes() if self._reference_path.exists() else None
        switched = False
        try:
            self._create(incoming, "dem-beta:base:" + self.settings.commit)
            self.builder(incoming)
            self._grant(incoming)
            inspection = self._inspect_content(incoming)
            self.hook("after_validation")
            self.control.exec_driver_sql(f"REVOKE CONNECT ON DATABASE {self._database(incoming)} FROM {self._quote(self.settings.app)}")
            self._allow(incoming, False)
            had_old = self._rename_pair(current, incoming, old)
            switched = True
            self.hook("after_swap")
            row = self._require(current)
            self._json(self._reference_path, {**inspection, "oid": row["oid"], "marker": row["marker"]})
            self.hook("before_drop_old")
            self._drop(old)
            return {"ok": True, "base_commit": self.settings.commit}
        except Exception:
            if switched:
                self._rollback_pair(current, incoming, old, had_old)
                self._restore_file(self._reference_path, previous)
            self._drop(incoming)
            raise

    def _start_prepare(self):
        if self._flag.exists() or self._prepared_path.exists():
            raise AdminError("a maintenance operation is already pending")
        self.settings.flag_dir.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        with self._flag.open("x", encoding="utf-8") as output:
            output.write(token)
        return token

    def _remove_flag(self, token):
        if self._flag.read_text(encoding="utf-8") != token:
            raise AdminError("maintenance marker was replaced; refusing to remove it")
        self._flag.unlink()

    def _prepare(self):
        reference = self._reference()
        return self._prepare_candidate(reference, None)

    def _prepare_candidate(self, reference, dump):
        incoming = self.names.name("live_next")
        token = self._start_prepare()
        try:
            marker = "dem-beta:live:" + self._marker(self.names.name("base")) + ":" + datetime.now(UTC).isoformat()
            self._create(incoming, marker, None if dump else self.names.name("base"))
            if dump:
                self._utility("pg_restore", incoming, ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname", incoming, str(dump)])
            self._grant(incoming)
            inspection = self._inspect_content(incoming, live=dump is not None)
            if dump is None and (inspection["releases"] != reference["releases"] or inspection["counts"] != reference["counts"]):
                raise AdminError("candidate differs from the sealed base")
            self.hook("after_validation")
            row = self._require(incoming)
            self._json(self._prepared_path, {"phase": "prepared", "token": token, "oid": row["oid"], "marker": row["marker"],
                "base_oid": reference["oid"], "mode": "restore" if dump else "reset"})
            return {"ok": True, "prepared": True}
        except Exception:
            self._drop(incoming)
            self._prepared_path.unlink(missing_ok=True)
            self._remove_flag(token)
            raise

    def _api_connected(self):
        return bool(self.control.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=ANY(:names) AND usename=:role)"),
            {"names": [self.names.name("live"), self.names.name("live_next")], "role": self.settings.app}))

    def _swap(self):
        state = json.loads(self._prepared_path.read_text(encoding="utf-8"))
        if state["phase"] != "prepared" or self._flag.read_text(encoding="utf-8") != state["token"]:
            raise AdminError("live swap has no matching prepared maintenance operation")
        reference = self._reference()
        incoming, current, old = (self.names.name(s) for s in ("live_next", "live", "live_old"))
        candidate = self._require(incoming)
        if (candidate["oid"], candidate["marker"], reference["oid"]) != (state["oid"], state["marker"], state["base_oid"]):
            raise AdminError("prepared database or base changed")
        previous_status = self.settings.status_file.read_bytes() if self.settings.status_file.exists() else None
        switched = False
        current_exists = self._info(current) is not None
        try:
            if self._api_connected():
                raise AdminError("API connections remain; stop the API before swapping")
            if current_exists:
                self._dump(current, "preswap", 1)
                self._allow(current, False)
            self._allow(incoming, False)
            if self._api_connected():
                raise AdminError("API reconnected during swap preparation")
            # Recheck immediately before closing the candidate to all clients.
            self._allow(incoming, True)
            inspection = self._inspect_content(incoming, live=state["mode"] == "restore")
            if state["mode"] == "reset" and inspection["releases"] != reference["releases"]:
                raise AdminError("candidate release set differs from the sealed base")
            self._allow(incoming, False)
            had_old = self._rename_pair(current, incoming, old)
            switched = True
            self.hook("after_swap")
            now = datetime.now(UTC)
            self._json(self.settings.status_file, {"last_reset_at": now.isoformat(), "next_reset_at": next_reset(now, self.settings.schedule)})
            self._allow(current, True)
            self._json(self._prepared_path, {**state, "phase": "swapped"})
            self.hook("before_drop_old")
            self._drop(old)
            return {"ok": True, "swapped": True, "mode": state["mode"]}
        except Exception:
            if switched:
                self._allow(current, False)
                self._rollback_pair(current, incoming, old, had_old)
                self._restore_file(self.settings.status_file, previous_status)
            if current_exists:
                self._allow(current, True)
            self._drop(incoming)
            self._json(self._prepared_path, {**state, "phase": "failed_restored"})
            raise

    def _finish(self):
        state = json.loads(self._prepared_path.read_text(encoding="utf-8"))
        if state["phase"] not in ("swapped", "failed_restored"):
            raise AdminError("maintenance cannot finish before swap or recovery")
        self._remove_flag(state["token"])
        self._prepared_path.unlink()
        return {"ok": True, "maintenance": False}

    def _utility(self, utility, name, arguments):
        self._require(name)
        env = {key: value for key, value in os.environ.items() if key not in ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGDATABASE", "PGUSER", "PGHOST", "PGPORT")}
        env.update(PGHOST=self.url.host or "localhost", PGPORT=str(self.url.port or 5432), PGUSER=self.settings.owner, PGDATABASE=name)
        if self.settings.owner_password is not None:
            env["PGPASSWORD"] = self.settings.owner_password
        for key in ("sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout", "application_name"):
            if key in self.url.query:
                env["PGAPPNAME" if key == "application_name" else "PG" + key.upper()] = str(self.url.query[key])
        completed = subprocess.run([str(self._binary(utility)), "--no-password", *arguments], env=env, capture_output=True, timeout=540)
        if completed.returncode:
            raise AdminError(utility + " failed; private driver diagnostics were suppressed")

    def _backup_files(self, kind):
        directory = self.settings.backup_dir
        if not directory.exists():
            return []
        return sorted(path for path in directory.iterdir() if not path.is_symlink() and path.is_file() and BACKUP.fullmatch(path.name) and path.name.startswith("dem-beta-" + kind + "-"))

    def _dump(self, name, kind, retain):
        self._require(name)
        self.settings.backup_dir.mkdir(parents=True, exist_ok=True)
        basename = f"dem-beta-{kind}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.dump"
        destination = self.settings.backup_dir / basename
        temporary = destination.with_suffix(".partial")
        try:
            self._utility("pg_dump", name, ["-Fc", "--dbname", name, "--file", str(temporary)])
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise AdminError("empty database dump")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        for path in self._backup_files(kind)[:-retain]:
            path.unlink()
        return destination

    def _backup(self):
        path = self._dump(self.names.name("live"), "backup", 7)
        return {"ok": True, "backup": path.name}

    def _restore(self, dump):
        if dump is None or not Path(dump).is_file() or Path(dump).is_symlink():
            raise AdminError("restore requires a regular dump file")
        self._prepare_candidate(self._reference(), Path(dump).resolve())
        return self._swap()

    def _status(self):
        result = {"ok": True, "databases": {}, "reset": None, "latest_backup": None}
        for suffix in ("base", "live"):
            name = self.names.name(suffix)
            row = self._info(name)
            if row:
                self._marker(name, row)
                entry = {"marker": row["marker"], "allow_connections": row["datallowconn"]}
                if suffix == "base":
                    reference = self._reference()
                    entry.update(counts=reference["counts"], published_releases=len(reference["releases"]), bytes=reference["bytes"])
                else:
                    engine = self._data_engine(name)
                    try:
                        with beta_base.readonly_session(engine) as session:
                            entry["bytes"] = session.scalar(text("SELECT pg_database_size(current_database())"))
                            entry["counts"] = {table: session.scalar(select(func.count()).select_from(Base.metadata.tables[table])) for table in ("formula", "theorem", "proof_step")}
                            release = Base.metadata.tables["package_release"]
                            entry["published_releases"] = session.scalar(select(func.count()).select_from(release).where(release.c.published_at.is_not(None)))
                    finally:
                        engine.dispose()
                result["databases"][suffix] = entry
        if self.settings.status_file.exists():
            result["reset"] = json.loads(self.settings.status_file.read_text(encoding="utf-8"))
        files = self._backup_files("backup")
        if files:
            result["latest_backup"] = files[-1].name
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("roles", "build-base", "backup", "status"):
        sub.add_parser(command)
    restore = sub.add_parser("restore")
    restore.add_argument("--file", type=Path, required=True)
    reset = sub.add_parser("reset")
    reset.add_argument("phase", choices=("prepare", "swap", "finish"))
    args = parser.parse_args(argv)
    admin = None
    try:
        if os.environ.get("DEM_BETA") != "1":
            raise AdminError("DEM_BETA=1 is required; nothing changed")
        admin = BetaAdmin(Settings.from_env())
        command = "reset " + args.phase if args.command == "reset" else args.command
        result = admin.execute(command, file=getattr(args, "file", None))
    except Exception as exc:
        result = {"ok": False, "error_type": type(exc).__name__}
        if isinstance(exc, AdminError):
            result["error"] = str(exc)
    finally:
        if admin:
            admin.close()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
