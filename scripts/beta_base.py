"""Build, freeze and inspect an existing, offline beta base database.

Run as ``python -m scripts.beta_base COMMAND --database-url URL``.
Database provisioning and replacement belong to the reset/deployment tools.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from sqlalchemy import CheckConstraint, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.inspection import _inspects
from sqlalchemy.orm import Session

from dem.db.engine import make_engine
from dem.db.models import Base, Package, PackageRelease
from dem.db import triggers
from dem.db.package_triggers import create_published_triggers
from dem.services.package import ENTITY_TABLES, dependency_closure, publish_release
from webapi.management.schema_revision import content_schema_head, upgrade_content_schema
from webapi.package_export import write_package_export


class BaseCheckError(ValueError):
    pass


class _DDLRecorder:
    """Run the shared installers against a recorder, never the database.

    Their pre-existing-row checks deliberately see no rows. Column discovery
    uses the real read-only inspector; every DDL statement is only collected.
    """
    def __init__(self, connection):
        self.dialect = connection.dialect
        self.inspector = inspect(connection)
        self.statements = []

    def exec_driver_sql(self, statement):
        self.statements.append(statement)

    def scalars(self, statement):
        return ()


@_inspects(_DDLRecorder)
def _inspect_recorder(recorder):
    return recorder.inspector


def expected_ddl(connection):
    recorder = _DDLRecorder(connection)
    triggers.create_tier_a_triggers(recorder)
    triggers.create_tier_b_wellformed_gate(recorder)
    triggers.create_tier_b_immutability_triggers(recorder)
    create_published_triggers(recorder)
    return recorder.statements


def _normalized(sql):
    # Preserve the contents of literals and quoted identifiers.
    parts = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\s+|[^\s'\"]+", sql.strip())
    return "".join(" " if part.isspace() else part for part in parts).rstrip("; ")


def check_triggers(connection):
    expected = expected_ddl(connection)
    failures = []
    checked = 0
    if connection.dialect.name == "sqlite":
        actual = dict(connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='trigger'")).all())
        for ddl in expected:
            match = re.search(r"CREATE TRIGGER IF NOT EXISTS (\w+)", ddl)
            if not match:
                raise BaseCheckError("unrecognized shared SQLite trigger DDL")
            name = match[1]
            canonical = ddl.replace(" IF NOT EXISTS", "", 1)
            if name not in actual or _normalized(actual[name]) != _normalized(canonical):
                failures.append(name)
            checked += 1
    elif connection.dialect.name == "postgresql":
        schema = connection.scalar(text("SELECT current_schema()"))
        rows = connection.execute(text("""
            SELECT t.tgname, pg_get_triggerdef(t.oid), t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE NOT t.tgisinternal AND n.nspname=current_schema()
        """))
        actual = {name: (ddl, enabled) for name, ddl, enabled in rows}
        functions = {}
        for row in connection.execute(text("""
            SELECT p.proname, pg_get_function_identity_arguments(p.oid), p.prosrc,
                   l.lanname, pg_get_function_result(p.oid), p.prosecdef,
                   p.proconfig, p.provolatile, p.proisstrict
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_language l ON l.oid=p.prolang
            WHERE n.nspname=current_schema()
        """)):
            functions[(row[0], row[1])] = tuple(row[2:])
        for ddl in expected:
            if ddl.lstrip().startswith("DROP "):
                continue
            # Installers group several CREATE FUNCTION statements in one call.
            matches = list(re.finditer(
                r"CREATE OR REPLACE FUNCTION (\w+)\((.*?)\)\s+RETURNS (\w+)\s+LANGUAGE (\w+)\s+(STABLE\s+)?AS \$\$(.*?)\$\$",
                ddl, re.S | re.I))
            if matches:
                for match in matches:
                    name, args, result, language, stable, body = match.groups()
                    row = functions.get((name, args))
                    wanted = (_normalized(body), language.lower(), result.lower(), False, None, "s" if stable else "v", False)
                    found = (_normalized(row[0]), *row[1:]) if row else None
                    if found != wanted:
                        failures.append("function:" + name)
                    checked += 1
                continue
            match = re.search(r"CREATE (?:CONSTRAINT )?TRIGGER (\w+).*?EXECUTE FUNCTION \w+\(\)", ddl, re.S)
            if not match:
                raise BaseCheckError("unrecognized shared PostgreSQL trigger DDL")
            name = match[1]
            row = actual.get(name)
            found = row[0].replace(schema + ".", "") if row else ""
            if not row or row[1] != "O" or _normalized(found) != _normalized(match[0]):
                failures.append(name)
            checked += 1
    else:
        raise BaseCheckError("unsupported database dialect")
    return {"ok": not failures, "checked": checked, "mismatches": failures}


def archive_digests(session):
    result = {}
    with TemporaryDirectory(prefix="dem-beta-verify-") as directory:
        target = Path(directory) / "release.dempkg"
        for release in session.scalars(select(PackageRelease).where(
            PackageRelease.published_at.is_not(None)).order_by(PackageRelease.id)):
            write_package_export(session, target, release.id)
            result[release.id] = hashlib.sha256(target.read_bytes()).hexdigest()
    return result


def _missing_roles(session):
    table = Base.metadata.tables["symbol_role"]
    allowed = None
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint):
            match = re.search(r"\brole\s+IN\s*\(([^)]+)\)", str(constraint.sqltext), re.I)
            if match:
                allowed = set(ast.literal_eval("(" + match[1] + ",)"))
    if allowed is None:
        raise BaseCheckError("cannot derive symbol roles from schema CHECK")
    return sorted(allowed - set(session.scalars(select(table.c.role))))


@contextmanager
def readonly_session(engine):
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        else:
            connection.exec_driver_sql("PRAGMA query_only=ON")
        try:
            with Session(bind=connection, autoflush=False) as session:
                yield session
        finally:
            connection.rollback()
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only=OFF")
                connection.rollback()


def release_snapshot(session, digests):
    return {json.dumps([name, version], separators=(",", ":")): digests[rid]
            for rid, name, version in session.execute(select(PackageRelease.id, Package.name, PackageRelease.version)
                .join(Package).where(PackageRelease.published_at.is_not(None)))}


def verify(engine, *, live_releases=None):
    with readonly_session(engine) as session:
        connection = session.connection()
        checks = {}
        tables = set(inspect(connection).get_table_names())
        revisions = list(connection.scalars(text("SELECT version_num FROM alembic_version"))) if "alembic_version" in tables else []
        checks["revision"] = {"ok": revisions == [content_schema_head()], "actual": revisions, "head": content_schema_head()}
        checks["triggers"] = check_triggers(connection)
        ownership = {}
        for name in ENTITY_TABLES:
            table = Base.metadata.tables[name]
            ownership[name] = list(session.scalars(select(table.c.id).outerjoin(
                PackageRelease, table.c.release_id == PackageRelease.id).where(
                    PackageRelease.published_at.is_(None)).order_by(table.c.id)))
        if live_releases is None:
            checks["ownership"] = {"ok": not any(ownership.values()), "unfrozen": ownership}
        digests = archive_digests(session)
        mismatches = [release.id for release in session.scalars(select(PackageRelease).where(
            PackageRelease.published_at.is_not(None))) if digests[release.id] != release.content_digest]
        checks["digests"] = {"ok": not mismatches, "actual": digests, "mismatches": mismatches}
        if live_releases is not None:
            actual = release_snapshot(session, digests)
            checks["base_releases"] = {"ok": actual == live_releases, "actual": actual, "expected": live_releases}
        unverified = list(connection.scalars(text(triggers.PROVEN_WITHOUT_VERIFIED_PROOF_SQL)))
        incomplete = [list(row) for row in connection.execute(text(triggers.INCOMPLETE_FORMULAS_SQL))]
        checks["mathematical_state"] = {"ok": not (unverified or incomplete), "proven_without_verified": unverified, "incomplete_formulas": incomplete}
        # ProofService.validate returns immediately for verified proofs. Import
        # reconstruction validates newly written proofs, not existing read-only
        # proofs. No existing read-only full-proof revalidation entry point.
        checks["proof_revalidation"] = {"available": False, "reason": "No existing read-only full-proof revalidation entry point; verified ProofService.validate is a no-op"}
        missing = _missing_roles(session)
        return {"ok": all(check.get("ok", True) for check in checks.values()),
                "checks": checks, "warnings": [{"missing_symbol_roles": missing}] if missing else []}


def publish_all(engine):
    """One transaction, exact dependency closure, dependencies published first."""
    with Session(engine) as session, session.begin():
        connection = session.connection()
        releases = list(session.scalars(select(PackageRelease).order_by(PackageRelease.id).with_for_update()))
        unpublished = {r.id for r in releases if r.published_at is None}
        if unpublished and (list(connection.execute(text(triggers.INCOMPLETE_FORMULAS_SQL))) or list(connection.execute(text(triggers.PROVEN_WITHOUT_VERIFIED_PROOF_SQL)))):
            raise BaseCheckError("incomplete formulas or proven theorem without verified proof")
        proof = Base.metadata.tables["proof"]
        if session.scalar(select(proof.c.id).where(proof.c.release_id.in_(unpublished), proof.c.status != "verified").limit(1)) is not None:
            raise BaseCheckError("base contains unfinished proofs")
        closures = {release.id: dependency_closure(session, release.id) - {release.id} for release in releases}
        completed = set()
        pending = {release.id for release in releases}
        while pending:
            ready = sorted(rid for rid in pending if closures[rid] <= completed)
            if not ready:
                raise BaseCheckError("unresolvable release dependency order")
            for rid in ready:
                publish_release(session, rid)
                completed.add(rid)
                pending.remove(rid)
        return {"ok": True, "published_or_checked": sorted(completed)}


def build(database_url):
    engine = existing_engine(database_url)
    try:
        with engine.connect() as connection:
            for name in inspect(connection).get_table_names():
                if name == "alembic_version":
                    continue
                quoted = connection.dialect.identifier_preparer.quote(name)
                if connection.scalar(text(f"SELECT 1 FROM {quoted} LIMIT 1")) is not None:
                    raise BaseCheckError("build requires an empty database: " + name)
        upgrade_content_schema(database_url)
        from dem.db.seeds import seed_all
        with Session(engine) as session, session.begin():
            seed_all(session)
        publish_all(engine)
        return verify(engine)
    finally:
        engine.dispose()


def existing_engine(database_url):
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and (not url.database or url.database == ":memory:" or not Path(url.database).is_file()):
        raise BaseCheckError("SQLite destination must be an existing database file")
    return make_engine(database_url)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "publish-all", "verify"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base-json", type=Path)
    args = parser.parse_args(argv)
    if args.live and (args.command != "verify" or args.base_json is None):
        parser.error("--live requires verify and --base-json")
    try:
        if args.command == "build":
            result = build(args.database_url)
        else:
            engine = existing_engine(args.database_url)
            try:
                reference = json.loads(args.base_json.read_text(encoding="utf-8"))["releases"] if args.live else None
                if args.live and not isinstance(reference, dict):
                    raise BaseCheckError("invalid base reference")
                result = verify(engine, live_releases=reference) if args.command == "verify" else publish_all(engine)
            finally:
                engine.dispose()
    except Exception as exc:
        # URLs/credentials and database-driver diagnostics must not enter JSON.
        result = {"ok": False, "error_type": type(exc).__name__}
        if isinstance(exc, BaseCheckError):
            result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
