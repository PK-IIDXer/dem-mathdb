"""Safely upgrade all SQLite workspace databases registered in the management DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from webapi.management.deployment_lock import DeploymentLockBusy
from webapi.management.schema_upgrade import upgrade_all_workspaces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--management-database-url",
        default=os.environ.get("DEM_MANAGEMENT_DATABASE_URL"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workspace-id", action="append", type=UUID, default=[])
    args = parser.parse_args()
    if not args.management_database_url:
        parser.error(
            "--management-database-url or DEM_MANAGEMENT_DATABASE_URL is required"
        )
    try:
        results = upgrade_all_workspaces(
            args.management_database_url,
            dry_run=args.dry_run,
            workspace_ids=set(args.workspace_id) or None,
        )
    except DeploymentLockBusy as exc:
        print(json.dumps({"outcome": "busy", "detail": str(exc)}))
        return 2
    for result in results:
        print(json.dumps(result.__dict__, default=str, sort_keys=True))
    return 1 if any(result.outcome == "upgrade_blocked" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
