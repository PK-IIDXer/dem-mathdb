"""The axiom-introduction record and the import record (lean-import-design §2.8, §3.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import Base
from dem.db.seed import seed_language
from dem.types import SymbolTypeName, Token

REPO_ROOT = Path(__file__).resolve().parents[1]

_IMPORT_ROW = {
    "source_system": "example-prover",
    "source_system_version": "1.0",
    "library": "example-library",
    "library_version": "1.0",
    "library_commit": "0123456789abcdef0123456789abcdef01234567",
    "declaration": "example_declaration",
    "module": "Example.Logic.Core",
    "file": "Example/Logic/Core.example",
    "line": 1,
    "source_statement": "example source statement",
    "source_statement_hash": "0" * 64,
    "universe_params": 0,
    "source_axioms": "[]",
    "translator_version": "0",
    "mapping_table_version": "0",
    "prop_encoding": "[]",
    "check_model": "not_run",
    "check_roundtrip": "not_run",
    "license": "Apache-2.0",
    "upstream_origin": "unknown",
    "retrieved_at": "2026-09-23 00:00:00",
}


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys = ON")
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        yield DemServices(session)
    engine.dispose()


def _conjecture(dem: DemServices) -> int:
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    phi = dem.symbols.register("φ", kind.id, 0)
    formula = dem.formulas.register([Token(symbol_id=phi.id)])
    return dem.theorems.register("imported", formula.id).id


def _insert_import(dem: DemServices, theorem_id: int, **overrides: object) -> None:
    row = {**_IMPORT_ROW, "theorem_id": theorem_id, **overrides}
    columns = ", ".join(row)
    values = ", ".join(f":{name}" for name in row)
    with dem.session.begin_nested():
        dem.session.execute(text(f"INSERT INTO import_record ({columns}) VALUES ({values})"), row)


@pytest.mark.parametrize(
    "overrides",
    [
        {"check_model": "verified"},
        {"check_roundtrip": "proven"},
        {"upstream_origin": "llm"},
        {"line": 0},
        {"universe_params": -1},
    ],
)
def test_import_record_rejects_unknown_values(dem: DemServices, overrides) -> None:
    theorem_id = _conjecture(dem)
    _insert_import(dem, theorem_id)
    with pytest.raises(IntegrityError):
        _insert_import(dem, theorem_id, declaration="other", **overrides)


def test_import_record_is_unique_per_source_and_goes_with_its_conjecture(dem: DemServices) -> None:
    theorem_id = _conjecture(dem)
    _insert_import(dem, theorem_id)
    with pytest.raises(IntegrityError):
        _insert_import(dem, theorem_id)
    dem.session.execute(text("DELETE FROM theorem WHERE id = :id"), {"id": theorem_id})
    assert dem.session.scalar(text("SELECT COUNT(*) FROM import_record")) == 0


def test_nothing_writes_an_import_record_yet() -> None:
    """The importer is stage B; until then no production code names the table."""
    offenders = []
    for root in ("dem", "webapi", "scripts", "demlang"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            if path.name == "foundation_records.py" or path.parts[-2:] == ("models", "__init__.py"):
                continue
            source = path.read_text(encoding="utf-8")
            if "import_record" in source or "ImportRecord" in source:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
