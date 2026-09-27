r"""Build the public A-only workspace template database.

The output is a deployment artifact and is intentionally ignored by Git. Regenerate
the default artifact from the repository root with:

    .\.venv\Scripts\python.exe scripts\build_workspace_template.py build\template.db

The command creates ``template.db`` from the public seed and writes the production-code
fingerprint to ``template.db.fingerprint``. New workspaces copy the database; they do
not run seed code.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dem.api import DemApi
from dem.db.seeds import seed_all
from webapi.management.schema_revision import upgrade_content_schema
from webapi.management.workspace import write_template_fingerprint


def build_workspace_template(destination: Path) -> str:
    """Build and atomically publish an A-only SQLite template and fingerprint."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    temporary_fingerprint = temporary.with_name(f"{temporary.name}.fingerprint")
    try:
        database_url = f"sqlite+pysqlite:///{temporary.as_posix()}"
        upgrade_content_schema(database_url)
        api = DemApi.from_url(database_url)
        try:
            with api.transaction() as dem:
                seed_all(dem.session)
        finally:
            api.engine.dispose()
        fingerprint = write_template_fingerprint(temporary)
        os.replace(temporary, destination)
        os.replace(
            temporary_fingerprint,
            destination.with_name(f"{destination.name}.fingerprint"),
        )
        return fingerprint
    finally:
        temporary.unlink(missing_ok=True)
        temporary_fingerprint.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=Path("build/template.db"),
    )
    args = parser.parse_args()
    fingerprint = build_workspace_template(args.destination)
    print(f"built {args.destination} (public A-only, fingerprint {fingerprint})")


if __name__ == "__main__":
    main()
