"""Dev convenience: wipe the local database and reseed everything from scratch.

Usage:
    python -m dem.db.reset_db            # prompts for confirmation
    python -m dem.db.reset_db --yes      # skips the confirmation prompt

Respects DEM_DATABASE_URL the same way the seed_*.py scripts do; defaults to
the sqlite dev DB (./dem_dev.db). For sqlite this deletes the DB file (plus
any -wal/-shm sidecar files) before recreating the schema. Non-sqlite targets
(Postgres) are refused by default because deployed databases are managed with
`alembic upgrade head`; pass --force-non-sqlite only for a throwaway local
Postgres. The shared ``create_all()`` path installs the same Tier A triggers.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dem.api import DemApi
from dem.db.base import Base
from dem.db.seeds import seed_all


def _database_url() -> str:
    return os.environ.get("DEM_DATABASE_URL", "sqlite:///./dem_dev.db")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _sqlite_path(url: str) -> Path:
    # sqlite:///relative/path.db or sqlite:////absolute/path.db
    path = url.split("sqlite:///", 1)[1]
    return Path(path)


def _wipe_sqlite(url: str) -> None:
    db_path = _sqlite_path(url)
    for candidate in (db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        if candidate.exists():
            candidate.unlink()
            print(f"Deleted {candidate}")


def _confirm(url: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    answer = input(f"This will WIPE all data at {url!r} and reseed from scratch. Type 'yes' to continue: ")
    if answer.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(1)


def reset_and_reseed(url: str, force_non_sqlite: bool) -> None:
    is_sqlite = _is_sqlite(url)
    if not is_sqlite and not force_non_sqlite:
        print(
            f"Refusing to reset non-sqlite database {url!r}.\n"
            "Postgres deployments are managed via `alembic upgrade head`. Re-run with "
            "--force-non-sqlite if you really want to drop_all/create_all here "
            "(e.g. a throwaway local Postgres); create_all will install the shared "
            "Tier A triggers, or use alembic downgrade/upgrade instead."
        )
        sys.exit(1)

    connect_args = {"check_same_thread": False} if is_sqlite else {}

    if is_sqlite:
        _wipe_sqlite(url)
    else:
        wipe_engine = DemApi.from_url(url, connect_args=connect_args).engine
        Base.metadata.drop_all(wipe_engine)
        wipe_engine.dispose()
        print(f"Dropped all tables on {url!r}")

    api = DemApi.from_url(url, connect_args=connect_args)
    api.create_schema()

    with api.transaction() as dem:
        summary = seed_all(dem.session)

    print(
        "Reset complete. Seeded the public A-only language and Hilbert schemas: "
        f"{len(summary.axiom_names)} axioms, "
        f"{len(summary.axiom_system_names)} axiom systems, and "
        f"{len(summary.theorem_names)} theorems."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    parser.add_argument(
        "--force-non-sqlite",
        action="store_true",
        help="allow drop_all/create_all against a non-sqlite DEM_DATABASE_URL",
    )
    args = parser.parse_args()

    url = _database_url()
    _confirm(url, args.yes)
    reset_and_reseed(url, args.force_non_sqlite)


if __name__ == "__main__":
    main()
