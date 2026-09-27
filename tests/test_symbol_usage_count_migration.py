import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20260908_0001_symbol_usage_count.py"
    )
    spec = importlib.util.spec_from_file_location("symbol_usage_count", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_usage_count_migration_backfills_distinct_formulas() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    change = migration()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE symbol (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE formula_token (symbol_id INTEGER, formula_id INTEGER)"
        )
        connection.exec_driver_sql(
            "INSERT INTO symbol VALUES (1, 'x'), (2, 'y'), (3, 'unused')"
        )
        connection.exec_driver_sql(
            "INSERT INTO formula_token VALUES (1, 10), (1, 10), (1, 11), (2, 11)"
        )
        with Operations.context(MigrationContext.configure(connection)):
            change.upgrade()
            rows = connection.exec_driver_sql(
                "SELECT id, usage_count FROM symbol ORDER BY id"
            ).all()
            assert rows == [(1, 2), (2, 1), (3, 0)]
            change.downgrade()
        assert "usage_count" not in {
            column["name"] for column in inspect(connection).get_columns("symbol")
        }
    engine.dispose()
