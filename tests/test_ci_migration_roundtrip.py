"""Exercise the API image's nonempty migration round trip on SQLite locally."""
from pathlib import Path
import runpy

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

SEED_DATABASE = "sqlite"


def test_api_image_nonempty_migration_roundtrip(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[1]
    fixture = runpy.run_path(str(repository / ".github/scripts/migration_roundtrip.py"))
    url = "sqlite+pysqlite:///" + (tmp_path / "roundtrip.db").as_posix()
    monkeypatch.setenv("DEM_DATABASE_URL", url)
    config = Config(str(repository / "alembic.ini"))
    config.set_main_option("script_location", str(repository / "alembic"))

    def check(action):
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                fixture[action](connection)
        finally:
            engine.dispose()

    command.upgrade(config, "20260910_0001")
    check("seed")
    command.upgrade(config, "head")
    check("check_head")
    command.downgrade(config, "20260910_0001")
    check("check_base")
    command.upgrade(config, "head")
    check("check_head")
