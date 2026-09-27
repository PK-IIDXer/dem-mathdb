"""Build the public A-only seed in ``DEM_DATABASE_URL``."""

from __future__ import annotations

import os

from dem.api import DemApi
from dem.db.seeds import seed_all


def _database_url() -> str:
    return os.environ.get("DEM_DATABASE_URL", "sqlite:///./dem_dev.db")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def main() -> None:
    url = _database_url()
    connect_args = {"check_same_thread": False} if _is_sqlite(url) else {}
    api = DemApi.from_url(url, connect_args=connect_args)
    if _is_sqlite(url):
        api.create_schema()

    with api.transaction() as dem:
        summary = seed_all(dem.session)

    print(
        "Seeded the public A-only database: "
        f"{len(summary.axiom_names)} axioms, "
        f"{len(summary.axiom_system_names)} axiom systems, "
        f"{len(summary.theorem_names)} theorems."
    )


if __name__ == "__main__":
    main()
