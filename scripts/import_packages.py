"""Install a release or reconstruct an exact lock using mandatory L2 checks."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext

from dem.db.models import Base, Namespace
from dem.db.engine import make_engine
from dem.services.package import publish_release
from scripts.package_import import import_release, reconstruct_lock, read_lock, read_release
from scripts.import_workspace import peak_rss_bytes
from webapi.management.schema_revision import upgrade_content_schema, content_schema_head


def _prepare_database(url, empty):
    engine = make_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        if empty:
            with engine.connect() as connection:
                for table in Base.metadata.sorted_tables:
                    if table.name in tables and connection.execute(select(table).limit(1)).first():
                        raise ValueError("destination is not empty: " + table.name)
        if tables:
            # Import must not silently migrate an existing workspace before
            # its L1 checks. Migration is an explicit prerequisite there.
            with engine.connect() as connection:
                if MigrationContext.configure(connection).get_current_revision() != content_schema_head():
                    raise ValueError("existing destination must be migrated to head before import")
            return
        upgrade_content_schema(url)
        if not tables:
            # Only namespaces provisioned by migrations in this newly empty DB.
            with Session(engine) as session, session.begin():
                pending = {row.id: row for row in session.scalars(select(Namespace))}
                while pending:
                    parents = {row.parent_id for row in pending.values()}
                    leaves = [key for key in pending if key not in parents]
                    if not leaves:
                        raise ValueError("namespace cycle")
                    for key in leaves:
                        session.delete(pending.pop(key))
                    session.flush()
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("install", "reconstruct", "publish"))
    parser.add_argument("source", help="Archive path, lock path, or release integer ID")
    parser.add_argument("--archives", type=Path, help="Directory of .dempkg release archives")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.operation == "reconstruct" and not args.archives:
        parser.error("reconstruct requires --archives")
    if args.operation == "install":
        read_release(args.source)
    elif args.operation == "reconstruct":
        read_lock(args.source)
    else:
        int(args.source)
    if args.prepare_only:
        print(json.dumps({"status": "prepared", "operation": args.operation}))
        return
    started = perf_counter()
    report = {"status": "failed"}
    try:
        _prepare_database(args.database_url, args.operation == "reconstruct")
        engine = make_engine(args.database_url)
        try:
            with Session(engine) as session:
                if args.operation == "install":
                    report["releases"] = [asdict(import_release(session, Path(args.source)))]
                elif args.operation == "reconstruct":
                    report["releases"] = [asdict(row) for row in reconstruct_lock(session, Path(args.source), args.archives)]
                else:
                    with session.begin():
                        row = publish_release(session, int(args.source))
                        report["content_digest"] = row.content_digest
            report["status"] = "passed"
        finally:
            engine.dispose()
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["wall_seconds"] = perf_counter() - started
        report["peak_rss_bytes"] = peak_rss_bytes()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
