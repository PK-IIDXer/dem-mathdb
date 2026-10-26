"""PostgreSQL lifecycle tests, isolated from production names and roles."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text, event, Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from dem.db.models import Base, PackageRelease, Axiom
from dem.services.axiom import AxiomService
from dem.services.tag import TagService
from dem.db.package_triggers import create_published_triggers
from scripts import beta_base
from scripts.beta_admin import AdminError, BetaAdmin, Names, Settings, next_reset

pytestmark = pytest.mark.skipif(os.environ.get("DEM_TEST_DATABASE") != "postgresql", reason="PostgreSQL beta operations; SQLite is not supported")
from beta_fixture import base_phase
SEED_PHASE = base_phase()
BIN = Path("C:/Program Files/PostgreSQL/18/bin")
ADMIN_URL = "postgresql+psycopg://dem_dev@localhost:5432/postgres"


@pytest.fixture(scope="module")
def snapshot_dump(seed_snapshot_factory, tmp_path_factory):
    factory = seed_snapshot_factory.postgresql
    name = factory._worker_database("beta3a_source", factory.get(base_phase()))
    path = tmp_path_factory.mktemp("beta3a-source") / "snapshot.dump"
    env = dict(os.environ, PGHOST="localhost", PGPORT="5432", PGUSER="dem_dev", PGDATABASE=name)
    result = subprocess.run([str(BIN / "pg_dump.exe"), "--no-password", "-Fc", "--file", str(path)], env=env, capture_output=True, timeout=60)
    assert result.returncode == 0
    return path


@pytest.fixture
def operator(snapshot_dump, tmp_path, monkeypatch):
    monkeypatch.setenv("DEM_BETA", "1")
    config = Settings(ADMIN_URL, tmp_path / "flags", tmp_path / "status.json", tmp_path / "backups", tmp_path / "state",
        "a" * 40, BIN, owner="dem_dev", app="dem_dev", names=Names("dem_beta_test_" + uuid4().hex[:12]))
    admin = None
    def builder(name):
        admin._utility("pg_restore", name, ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname", name, str(snapshot_dump)])
        engine = admin._data_engine(name)
        try:
            beta_base.publish_all(engine)
        finally:
            engine.dispose()
    # Only the permission probe is substituted: local dem_dev cannot create
    # separate roles. Real kernel validation, triggers and archives remain.
    admin = BetaAdmin(config, builder=builder, permission_probe=lambda name: {"ok": True, "test_only": "no CREATEROLE; real role tests skipped separately"})
    try:
        yield admin
    finally:
        admin.hook = lambda stage: None
        with admin._operation():
            for suffix in ("live_old", "live_next", "live", "base_old", "base_next", "base"):
                admin._drop(config.names.name(suffix))
        admin.close()


def bootstrap(admin):
    assert admin.execute("build-base")["ok"]
    assert admin.execute("reset prepare")["prepared"]
    assert admin.execute("reset swap")["swapped"]
    assert admin._flag.exists()
    admin.execute("reset finish")


def live_engine(admin):
    return create_engine(admin.url.set(database=admin.names.name("live")), poolclass=NullPool)


def user_write(admin, name):
    engine = live_engine(admin)
    try:
        with Session(engine) as session, session.begin():
            TagService(session).get_or_create(name)
            formula_id = session.scalar(select(Axiom.formula_id).order_by(Axiom.id))
            AxiomService(session).register(name, formula_id)
    finally:
        engine.dispose()


def tags(admin):
    engine = live_engine(admin)
    try:
        with engine.connect() as connection:
            return set(connection.scalars(select(Base.metadata.tables["tag"].c.name)))
    finally:
        engine.dispose()


def test_build_reset_backup_restore_and_readonly_status(operator, tmp_path):
    admin = operator
    bootstrap(admin)
    before = admin.execute("status")
    assert not before["databases"]["base"]["allow_connections"]
    assert before["databases"]["live"]["published_releases"] == before["databases"]["base"]["published_releases"]
    user_write(admin, "before-backup")
    admin.execute("backup")
    dump = admin._backup_files("backup")[-1]
    user_write(admin, "after-backup")
    assert admin.execute("restore", file=dump)["mode"] == "restore"
    admin.execute("reset finish")
    assert "before-backup" in tags(admin) and "after-backup" not in tags(admin)
    reference = json.loads(admin._reference_path.read_text())
    engine = live_engine(admin)
    try:
        assert beta_base.verify(engine, live_releases=reference["releases"])["ok"]
        assert not beta_base.verify(engine)["checks"]["ownership"]["ok"]
        statements = []
        event.listen(admin.engine, "before_cursor_execute", lambda c, cursor, s, p, ctx, many: statements.append(s))
        state = admin.execute("status")
        assert state["latest_backup"] == dump.name and state["reset"]["next_reset_at"]
        assert not any(s.lstrip().split()[0] in {"CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE"} for s in statements)
        reference_path = tmp_path / "base.json"
        reference_path.write_text(json.dumps(reference))
        result = subprocess.run([sys.executable, "-m", "scripts.beta_base", "verify", "--database-url", engine.url.render_as_string(hide_password=False), "--live", "--base-json", str(reference_path)], capture_output=True, text=True, timeout=60)
        assert result.returncode == 0 and json.loads(result.stdout)["ok"]
    finally:
        engine.dispose()
    admin.execute("reset prepare")
    admin.execute("reset swap")
    admin.execute("reset finish")
    assert "before-backup" not in tags(admin)


@pytest.mark.parametrize("stage", ["after_validation", "after_first_rename", "after_swap", "before_drop_old"])
def test_failed_base_rebuild_preserves_original(operator, stage):
    admin = operator
    bootstrap(admin)
    reference = admin._reference_path.read_bytes()
    before = admin.execute("status")
    def fail(at):
        if at == stage:
            raise RuntimeError("injected base failure")
    admin.hook = fail
    with pytest.raises(RuntimeError):
        admin.execute("build-base")
    assert admin._reference_path.read_bytes() == reference
    after = admin.execute("status")
    for kind in ("base", "live"):
        assert after["databases"][kind]["marker"] == before["databases"][kind]["marker"]


def test_prepare_validation_failure_removes_next_and_flag(operator, monkeypatch):
    admin = operator
    bootstrap(admin)
    user_write(admin, "preserve-prepare-failure")
    def reject(*args, **kwargs):
        raise AdminError("injected verifier failure")
    monkeypatch.setattr(admin, "_inspect_content", reject)
    with pytest.raises(AdminError):
        admin.execute("reset prepare")
    assert "preserve-prepare-failure" in tags(admin) and not admin._flag.exists()
    with admin._operation():
        assert admin._info(admin.names.name("live_next")) is None


def test_failed_permission_probe_stops_preparation(operator):
    admin = operator
    bootstrap(admin)
    # Legacy privileges must also roll back if permission setup fails halfway.
    with admin._operation():
        admin.control.exec_driver_sql(f"GRANT TEMPORARY ON DATABASE {admin._database(admin.names.name('live'))} TO {admin._quote(admin.settings.app)}")
    def database_acl():
        engine = live_engine(admin)
        try:
            with engine.connect() as connection:
                return connection.scalar(text("SELECT datacl::text FROM pg_database WHERE datname=current_database()"))
        finally:
            engine.dispose()
    previous_acl = database_acl()
    def fail_grant(connection, cursor, statement, parameters, context, many):
        if statement.startswith("GRANT USAGE ON SCHEMA public"):
            raise RuntimeError("injected grant failure")
    event.listen(Engine, "before_cursor_execute", fail_grant)
    try:
        with pytest.raises(RuntimeError, match="grant failure"), admin._operation():
            admin._grant(admin.names.name("live"))
    finally:
        event.remove(Engine, "before_cursor_execute", fail_grant)
    assert database_acl() == previous_acl
    user_write(admin, "preserve-permission-failure")
    admin.permission_probe = lambda name: {"ok": False}
    with pytest.raises(AdminError, match="permission verification"):
        admin.execute("reset prepare")
    assert "preserve-permission-failure" in tags(admin) and not admin._flag.exists()


@pytest.mark.parametrize("stage", ["after_first_rename", "after_swap", "before_drop_old", "dump"])
def test_swap_failure_preserves_live_and_status(operator, stage, monkeypatch):
    admin = operator
    bootstrap(admin)
    user_write(admin, "preserve-swap-failure")
    old_status = admin.settings.status_file.read_bytes()
    old_marker = admin.execute("status")["databases"]["live"]["marker"]
    admin.execute("reset prepare")
    if stage == "dump":
        monkeypatch.setattr(admin, "_utility", lambda *args: (_ for _ in ()).throw(AdminError("injected pg_dump failure")))
    else:
        admin.hook = lambda at: (_ for _ in ()).throw(RuntimeError("injected swap failure")) if at == stage else None
    with pytest.raises((RuntimeError, AdminError)):
        admin.execute("reset swap")
    assert "preserve-swap-failure" in tags(admin)
    assert admin.execute("status")["databases"]["live"]["marker"] == old_marker
    assert admin.settings.status_file.read_bytes() == old_status
    assert admin._flag.exists()
    admin.execute("reset finish")
    with admin._operation():
        assert admin._info(admin.names.name("live_old")) is None and admin._info(admin.names.name("live_next")) is None


def test_wrong_marker_refuses_every_write(operator):
    admin = operator
    bootstrap(admin)
    with admin._operation():
        name = admin.names.name("live_next")
        admin._create(name, "dem-beta:live:" + "a" * 40 + ":2026-01-01T00:00:00+00:00")
        admin._comment(name, "some-other-application")
    original = admin._reference_path.read_bytes()
    try:
        with pytest.raises(AdminError, match="marker"):
            admin.execute("reset prepare")
        assert not admin._flag.exists() and admin._reference_path.read_bytes() == original
    finally:
        with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f"COMMENT ON DATABASE {admin._quote(name)} IS 'dem-beta:live:{'a'*40}:2026-01-01T00:00:00+00:00'")


def test_disabled_beta_does_nothing(operator, monkeypatch):
    admin = operator
    monkeypatch.delenv("DEM_BETA")
    with pytest.raises(AdminError, match="DEM_BETA"):
        admin.execute("build-base")
    assert not admin.settings.state_dir.exists() and not admin.settings.flag_dir.exists()
    monkeypatch.setenv("DEM_BETA", "1")


def test_active_api_connection_prevents_swap(operator):
    admin = operator
    bootstrap(admin)
    user_write(admin, "preserve-active-api")
    admin.execute("reset prepare")
    engine = live_engine(admin)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            with pytest.raises(AdminError, match="API connections"):
                admin.execute("reset swap")
        assert "preserve-active-api" in tags(admin)
        with admin._operation():
            assert admin._info(admin.names.name("live_next")) is None
        admin.execute("reset finish")
        admin.execute("reset prepare")
        assert admin.execute("reset swap")["swapped"]
        admin.execute("reset finish")
    finally:
        engine.dispose()


def test_tampered_dump_with_forged_digest_never_becomes_live(operator):
    admin = operator
    bootstrap(admin)
    with admin._operation():
        engine = admin._data_engine(admin.names.name("live"))
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("DROP TRIGGER published_theorem_update ON theorem")
                connection.exec_driver_sql("DROP TRIGGER published_package_release_update ON package_release")
                connection.exec_driver_sql("UPDATE theorem SET description='tampered backup' WHERE id=(SELECT MIN(id) FROM theorem)")
            with Session(engine) as session, session.begin():
                for rid, digest in beta_base.archive_digests(session).items():
                    session.get(PackageRelease, rid).content_digest = digest
            with engine.begin() as connection:
                # Lifecycle fixture uses one local role for owner and app. Its
                # app ACL reset also removed TRIGGER from that same role; only
                # this deliberate tampering helper grants it back to rebuild
                # the original guards before exporting the adversarial dump.
                connection.exec_driver_sql(f"GRANT TRIGGER ON ALL TABLES IN SCHEMA public TO {admin._quote(admin.settings.owner)}")
                create_published_triggers(connection)
            assert beta_base.verify(engine)["ok"]
        finally:
            engine.dispose()
        dump = admin._dump(admin.names.name("live"), "backup", 7)
    admin.execute("reset prepare")
    admin.execute("reset swap")
    admin.execute("reset finish")
    user_write(admin, "must-survive-rejected-restore")
    with pytest.raises(AdminError, match="verification failed|differs"):
        admin.execute("restore", file=dump)
    assert "must-survive-rejected-restore" in tags(admin) and not admin._flag.exists()


def test_backup_retention_only_removes_tool_filenames(operator):
    admin = operator
    bootstrap(admin)
    directory = admin.settings.backup_dir
    directory.mkdir(exist_ok=True)
    for index in range(8):
        (directory / f"dem-beta-backup-20260101T00000000000{index}Z-12345678.dump").write_bytes(b"old test dump")
    unrelated = directory / "important.dump"
    unrelated.write_bytes(b"keep")
    admin.execute("backup")
    assert len(admin._backup_files("backup")) == 7 and unrelated.read_bytes() == b"keep"
    admin.execute("reset prepare")
    admin.execute("reset swap")
    admin.execute("reset finish")
    assert len(admin._backup_files("preswap")) == 1


def test_names_schedule_and_cli_secret_redaction(operator, monkeypatch, capsys):
    from dataclasses import replace
    with pytest.raises(AdminError, match="unsupported connection overrides"):
        BetaAdmin(replace(operator.settings, admin_url=ADMIN_URL + "?dbname=unrelated_database"))
    with pytest.raises(AdminError):
        Names("postgres")
    with pytest.raises(AdminError):
        operator._database("unrelated_database")
    with monkeypatch.context() as scoped:
        scoped.setattr(operator, "url", operator.url.set(password="test-only-sentinel"))
        scoped.setattr(operator, "_require", lambda name: None)
        for app in (False, True):
            engine = operator._data_engine(operator.names.name("live"), app=app)
            assert engine.url.password is None
            engine.dispose()
    now = datetime(2026, 10, 25, 20, tzinfo=timezone.utc)
    assert next_reset(now, "Mon 04:00 Asia/Tokyo") == "2026-11-01T19:00:00+00:00"
    assert next_reset(datetime(2026, 11, 1, 5, 15, tzinfo=timezone.utc), "Sun 01:30 America/New_York") == "2026-11-01T05:30:00+00:00"
    assert next_reset(datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc), "Sun 01:30 America/New_York") == "2026-11-08T06:30:00+00:00"
    with pytest.raises(AdminError, match="does not exist"):
        next_reset(datetime(2026, 3, 7, tzinfo=timezone.utc), "Sun 02:30 America/New_York")
    from scripts.beta_admin import main
    monkeypatch.delenv("DEM_BETA")
    monkeypatch.setenv("DEM_BETA_ADMIN_DATABASE_URL", "postgresql://secret:do-not-print@host/postgres")
    assert main(["status"]) == 1
    output = capsys.readouterr().out
    assert "secret" not in output and "do-not-print" not in output
    monkeypatch.setenv("DEM_BETA", "1")


def test_real_role_permissions_require_createrole(operator):
    with operator.engine.connect() as connection:
        privileged = connection.scalar(text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname=current_user"))
    if not privileged:
        pytest.skip("dem_dev has no CREATEROLE/SUPERUSER; role creation, timeouts and actual API-role DDL denials require staging")
    pytest.skip("Local role/authentication changes are excluded; run production role and permission probes in staging")
