"""Export one existing release without installing, publishing or changing it."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.engine import make_engine
from dem.db.models import Package, PackageRelease
from webapi.package_export import write_package_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    parser.add_argument("version")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    engine = make_engine(args.database_url)
    try:
        with Session(engine) as session:
            release = session.scalar(select(PackageRelease.id).join(Package, Package.id == PackageRelease.package_id).where(Package.name == args.package, PackageRelease.version == args.version))
            if release is None:
                parser.error("release does not exist in this database")
            result = write_package_export(session, args.destination, release)
            print(json.dumps({"path": str(result.path), "bytes": result.path.stat().st_size, "counts": result.row_counts}, sort_keys=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
