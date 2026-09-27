import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from dem.db.models import Base


def migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20260906_0001_formula_symbol_index.py"
    spec = importlib.util.spec_from_file_location("formula_symbol_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_database_has_covering_symbol_index():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    indexes = {row["name"]: row["column_names"] for row in inspect(engine).get_indexes("formula_token")}
    assert indexes["ix_formula_token_symbol_formula"] == ["symbol_id", "formula_id"]
    with engine.connect() as connection:
        plan = connection.exec_driver_sql(
            "EXPLAIN QUERY PLAN SELECT formula_id FROM formula_token WHERE symbol_id = 1").all()
        assert "ix_formula_token_symbol_formula" in str(plan)
    engine.dispose()


def test_index_migration_up_and_down_preserve_existing_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    change = migration()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE formula_token (symbol_id INTEGER, formula_id INTEGER)")
        connection.exec_driver_sql("INSERT INTO formula_token VALUES (3, 7), (3, 7), (4, 9)")
        original = connection.exec_driver_sql("SELECT * FROM formula_token").all()
        with Operations.context(MigrationContext.configure(connection)):
            change.upgrade()
            assert inspect(connection).get_indexes("formula_token")[0]["column_names"] == ["symbol_id", "formula_id"]
            change.downgrade()
            assert inspect(connection).get_indexes("formula_token") == []
        assert connection.exec_driver_sql("SELECT * FROM formula_token").all() == original
    engine.dispose()


def test_index_migration_generates_postgresql_ddl():
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration().upgrade()
    assert "CREATE INDEX ix_formula_token_symbol_formula ON formula_token (symbol_id, formula_id)" in output.getvalue()
