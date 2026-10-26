"""Import an exported workspace into an empty database, with mandatory L2.

Run with .venv\\Scripts\\python.exe -m scripts.import_workspace --help.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from dem.db.base import Base
from dem.db.models.language import Namespace

from dem.db.engine import make_engine
from webapi.management.schema_revision import upgrade_content_schema
from webapi.workspace_export import WorkspaceExportMetadata, write_workspace_export
from scripts.workspace_import import import_workspace


def peak_rss_bytes():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                        *[(name, ctypes.c_size_t) for name in (
                            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                            'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--database-url', required=True, help='Empty destination content DB; never an existing workspace')
    parser.add_argument('--source-database-url', help='Optionally export this existing seeded DB first')
    parser.add_argument('--roundtrip', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true', help='Check arguments and hash an existing archive; do not connect or write DBs')
    args = parser.parse_args()
    if len({args.archive.resolve(), args.roundtrip.resolve(), args.report.resolve()}) != 3:
        parser.error('archive, roundtrip and report must be different files')
    if args.source_database_url == args.database_url:
        parser.error('source and destination databases must differ')
    if args.prepare_only:
        print(json.dumps({'status': 'prepared', 'archive_exists': args.archive.exists(),
            'sha256': hashlib.sha256(args.archive.read_bytes()).hexdigest() if args.archive.exists() else None,
            'source_export_requested': bool(args.source_database_url)}, indent=2))
        return
    start = perf_counter()
    report = {'status': 'failed'}
    try:
        if args.source_database_url:
            if args.archive.exists():
                parser.error('refusing to overwrite source export archive')
            source_engine = make_engine(args.source_database_url)
            try:
                with Session(source_engine) as session:
                    write_workspace_export(session, args.archive, WorkspaceExportMetadata('workspace.measurement', 'Package L2 roundtrip measurement'))
            finally:
                source_engine.dispose()
        engine = make_engine(args.database_url)
        try:
            # Reject an occupied destination before Alembic can change it.
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as connection:
                for table in Base.metadata.sorted_tables:
                    if table.name in tables and connection.execute(select(1).select_from(table).limit(1)).first():
                        raise ValueError(f'destination is not empty: {table.name}')
            upgrade_content_schema(args.database_url)
            # Migrations provision namespace metadata even in an empty database.
            # Preflight above proved that no pre-existing content rows exist.
            # Remove only those migration-created namespaces, child-first, so
            # the atomic importer still requires every content table to be empty.
            with Session(engine) as preparation, preparation.begin():
                pending = {row.id: row for row in preparation.scalars(select(Namespace))}
                while pending:
                    parents = {row.parent_id for row in pending.values()}
                    leaves = [key for key in pending if key not in parents]
                    if not leaves:
                        raise ValueError('cycle in migration-created namespaces')
                    for key in leaves:
                        preparation.delete(pending.pop(key))
                    preparation.flush()
            with Session(engine) as session:
                result = import_workspace(session, args.archive)
                report.update(asdict(result))
                write_workspace_export(session, args.roundtrip, result.metadata)
        finally:
            engine.dispose()
        report['byte_identical'] = args.archive.read_bytes() == args.roundtrip.read_bytes()
        if not report['byte_identical']:
            raise RuntimeError('roundtrip bytes differ')
        report['status'] = 'passed'
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        report['wall_seconds'] = perf_counter() - start
        report['peak_rss_bytes'] = peak_rss_bytes()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
