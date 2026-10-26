"""Offline base publication and read-only inspection, without seed_all."""
import json
import subprocess
import sys

import pytest
from sqlalchemy import event, select, text

from dem.db.models import Base, Package, PackageRelease, ReleaseDependency, ReleaseLockEntry
from scripts import beta_base
from beta2_support import base_api, published_api, report, digests

from beta_fixture import base_phase
SEED_PHASE = base_phase()


def test_publish_verify_and_cli(published_api):
    api = published_api
    before = digests(api)
    with api.session() as dem:
        publications = [(r.id, r.published_at, r.content_digest, r.manifest) for r in dem.session.scalars(select(PackageRelease))]
    assert beta_base.publish_all(api.engine)["ok"]
    with api.session() as dem:
        assert publications == [(r.id, r.published_at, r.content_digest, r.manifest) for r in dem.session.scalars(select(PackageRelease))]
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(api.engine, "before_cursor_execute", record)
    try:
        result = beta_base.verify(api.engine)
    finally:
        event.remove(api.engine, "before_cursor_execute", record)
    assert result["ok"], result
    assert result["checks"]["digests"]["actual"] == before
    assert not any(s.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"} for s in statements)
    url = api.engine.url.render_as_string(hide_password=False)
    completed = subprocess.run([sys.executable, "-m", "scripts.beta_base", "verify", "--database-url", url], capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    cli = json.loads(completed.stdout)
    assert cli["ok"] and cli["checks"]["digests"]["actual"] == {str(key): value for key, value in before.items()}
    report("verify-" + api.engine.dialect.name, cli)


def test_build_refuses_nonempty_before_migration_or_seed(base_api, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("must reject before migration or seed")
    monkeypatch.setattr(beta_base, "upgrade_content_schema", forbidden)
    before = digests(base_api)
    with pytest.raises(beta_base.BaseCheckError, match="empty database"):
        beta_base.build(base_api.engine.url.render_as_string(hide_password=False))
    assert digests(base_api) == before


def test_unpublished_ownership_fails_verify(base_api):
    result = beta_base.verify(base_api.engine)
    assert not result["ok"] and not result["checks"]["ownership"]["ok"]
    assert any(result["checks"]["ownership"]["unfrozen"].values())


def test_publish_all_rolls_back_every_release_on_failure(base_api, monkeypatch):
    original = beta_base.publish_release
    seen = []
    def fail_late(session, release_id):
        original(session, release_id)
        seen.append(release_id)
        raise beta_base.BaseCheckError("injected failure after publication")
    monkeypatch.setattr(beta_base, "publish_release", fail_late)
    with pytest.raises(beta_base.BaseCheckError):
        beta_base.publish_all(base_api.engine)
    assert seen
    with base_api.session() as dem:
        assert all(r.published_at is None and r.content_digest is None and "_archive_catalogs" not in r.manifest
                   for r in dem.session.scalars(select(PackageRelease)))
    monkeypatch.setattr(beta_base, "publish_release", original)
    with base_api.transaction() as dem:
        from dem.db.models import Axiom
        axiom = dem.session.scalar(select(Axiom).order_by(Axiom.id))
        draft = dem.theorems.register("unfinished-base-proof-probe", axiom.formula_id)
        draft.release_id = axiom.release_id
        proof = dem.proofs.create_proof(draft.id)
        proof.release_id = axiom.release_id
    with pytest.raises(beta_base.BaseCheckError, match="unfinished proofs"):
        beta_base.publish_all(base_api.engine)
    with base_api.session() as dem:
        assert all(r.published_at is None for r in dem.session.scalars(select(PackageRelease)))
    # Already published releases receive only a digest check, including frozen
    # draft content permitted by the existing general-purpose publisher.
    with base_api.transaction() as dem:
        releases = list(dem.session.scalars(select(PackageRelease.id)))
        for rid in sorted(releases, key=lambda rid: (len(beta_base.dependency_closure(dem.session, rid)), rid)):
            original(dem.session, rid)
    before = digests(base_api)
    assert beta_base.publish_all(base_api.engine)["ok"]
    assert digests(base_api) == before


@pytest.mark.parametrize("damage", ["missing", "definition", "function", "disabled"])
def test_trigger_definition_inspection(published_api, damage):
    engine = published_api.engine
    dialect = engine.dialect.name
    if dialect == "sqlite" and damage in {"function", "disabled"}:
        pytest.skip("SQLite has no separate trigger functions or enabled flags")
    name, table = "published_symbol_update", "symbol"
    with engine.begin() as connection:
        if damage == "disabled":
            connection.exec_driver_sql(f"ALTER TABLE {table} DISABLE TRIGGER {name}")
        elif damage == "function":
            connection.exec_driver_sql(f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
        else:
            connection.exec_driver_sql(f"DROP TRIGGER {name}" + (f" ON {table}" if dialect == "postgresql" else ""))
            if damage == "definition":
                if dialect == "sqlite":
                    connection.exec_driver_sql(f"CREATE TRIGGER {name} BEFORE UPDATE ON {table} BEGIN SELECT 1; END")
                else:
                    connection.exec_driver_sql(f"CREATE TRIGGER {name} AFTER UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()")
    result = beta_base.verify(engine)
    assert not result["ok"] and not result["checks"]["triggers"]["ok"], result


def test_tampered_content_changes_rebuilt_digest(published_api):
    before = digests(published_api)
    with published_api.engine.begin() as connection:
        name = "published_theorem_update"
        connection.exec_driver_sql("DROP TRIGGER " + name + (" ON theorem" if connection.dialect.name == "postgresql" else ""))
        connection.execute(text("UPDATE theorem SET description='tampered' WHERE id=(SELECT MIN(id) FROM theorem)"))
    result = beta_base.verify(published_api.engine)
    assert digests(published_api) != before
    assert not result["checks"]["digests"]["ok"], result


def test_missing_sqlite_file_is_not_created(tmp_path):
    target = tmp_path / "absent.db"
    with pytest.raises(beta_base.BaseCheckError):
        beta_base.existing_engine("sqlite:///" + target.as_posix())
    assert not target.exists()


def test_dependency_publication_order_and_late_rollback(base_api, monkeypatch):
    with base_api.transaction() as dem:
        root = dem.session.scalar(select(PackageRelease).order_by(PackageRelease.id))
        package = Package(name="test.dependent", owner="test", visibility="private")
        dem.session.add(package)
        dem.session.flush()
        release = PackageRelease(package_id=package.id, version="1.0.0", dem_runtime_range=root.dem_runtime_range, manifest={})
        dem.session.add(release)
        dem.session.flush()
        dem.session.add(ReleaseDependency(release_id=release.id, depends_package_id=root.package_id, range="=" + root.version))
        dem.session.add(ReleaseLockEntry(release_id=release.id, locked_release_id=root.id))
        root_id, dependent_id = root.id, release.id
    original = beta_base.publish_release
    seen = []
    def fail_after_dependent(session, rid):
        closure = beta_base.dependency_closure(session, rid) - {rid}
        assert all(session.get(PackageRelease, dep).published_at is not None for dep in closure)
        original(session, rid)
        seen.append(rid)
        if rid == dependent_id:
            raise beta_base.BaseCheckError("failure after dependency and dependent")
    monkeypatch.setattr(beta_base, "publish_release", fail_after_dependent)
    with pytest.raises(beta_base.BaseCheckError):
        beta_base.publish_all(base_api.engine)
    assert seen.index(root_id) < seen.index(dependent_id)
    with base_api.session() as dem:
        assert all(r.published_at is None for r in dem.session.scalars(select(PackageRelease)))
    monkeypatch.setattr(beta_base, "publish_release", original)
    assert beta_base.publish_all(base_api.engine)["ok"]


def test_missing_dependency_pin_publishes_nothing(base_api):
    with base_api.transaction() as dem:
        root = dem.session.scalar(select(PackageRelease).order_by(PackageRelease.id))
        package = Package(name="test.missing-pin", owner="test", visibility="private")
        dem.session.add(package)
        dem.session.flush()
        dem.session.add(ReleaseDependency(release_id=root.id, depends_package_id=package.id, range="=1.0.0"))
    with pytest.raises(ValueError, match="missing exact dependency pin"):
        beta_base.publish_all(base_api.engine)
    with base_api.session() as dem:
        assert all(r.published_at is None for r in dem.session.scalars(select(PackageRelease)))


def test_skip_one_publication_fails_ownership(base_api, monkeypatch):
    original = beta_base.publish_release
    skipped = []
    def skip_one(session, rid):
        if not skipped:
            skipped.append(rid)
        else:
            original(session, rid)
    monkeypatch.setattr(beta_base, "publish_release", skip_one)
    beta_base.publish_all(base_api.engine)
    result = beta_base.verify(base_api.engine)
    assert skipped and not result["checks"]["ownership"]["ok"], result


def test_role_warnings_derive_schema_roles(base_api):
    with base_api.engine.begin() as connection:
        table = Base.metadata.tables["symbol_role"]
        role = connection.scalar(select(table.c.role).order_by(table.c.role))
        connection.execute(table.delete().where(table.c.role == role))
    beta_base.publish_all(base_api.engine)
    result = beta_base.verify(base_api.engine)
    assert result["ok"], result
    assert role in result["warnings"][0]["missing_symbol_roles"]
