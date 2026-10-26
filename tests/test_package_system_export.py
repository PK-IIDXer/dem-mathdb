"""Adversarial coverage of the package reconstruction comparison boundary."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_package_import import releases
from test_workspace_import import engines
from dem.db.models import Formula, Symbol
from dem.services.formula import FormulaService
from dem.types import Token
from scripts.package_import import reconstruct_lock
from webapi.workspace_export import write_workspace_export
import package_system_export as boundary


def test_orphan_is_excluded_but_missing_definition_body_is_detected(
    releases, engines, tmp_path, monkeypatch
):
    paths, whole, metadata = releases
    lock = {"schema_version": 1,
            "packages": {"example.base": "1.0.0", "example.leaf": "1.0.0"}}
    with Session(engines()) as source:
        reconstruct_lock(source, lock, paths[0].parent)
        assert boundary.orphan_formula_public_ids(source) == frozenset()
        phi = source.scalar(select(Symbol).where(Symbol.name == "phi"))
        wrap = source.scalar(select(Symbol).where(Symbol.name == "wrap"))
        orphan = FormulaService(source).register([
            Token(symbol_id=wrap.id), Token(symbol_id=wrap.id), Token(symbol_id=phi.id)])
        source.flush()
        excluded = boundary.orphan_formula_public_ids(source)
        assert excluded == {orphan.public_id}
        full, expected = tmp_path / "with-orphan.dempkg", tmp_path / "system.dempkg"
        write_workspace_export(source, full, metadata)
        counts = boundary.without_formulas(full, expected, excluded)
        assert counts == {"formulas.jsonl": 1, "formula_tokens.jsonl": 3}
        assert full.read_bytes() != whole.read_bytes()
        boundary.assert_same_system(whole, expected)

        # This body has no direct FK: the independent assertion must catch a
        # collector that mistakes it for an orphan by dropping its source kind.
        direct = set().union(*(boundary._joined_formula_ids(source, table, fk)
                               for table, fk in boundary._formula_constraints()))
        implicit = set(boundary._definition_bodies(source)) - direct
        assert implicit
        body_public_id = source.get(Formula, min(implicit)).public_id
        original_groups = boundary._reference_groups
        with monkeypatch.context() as mutation:
            mutation.setattr(boundary, "_reference_groups", lambda session: (
                (name, ids) for name, ids in original_groups(session)
                if name != "definition bodies"))
            with pytest.raises(AssertionError, match="excluded definition body"):
                boundary.orphan_formula_public_ids(source)

    with Session(engines()) as rebuilt:
        reconstruct_lock(rebuilt, lock, paths[0].parent)
        actual = tmp_path / "rebuilt.dempkg"
        write_workspace_export(rebuilt, actual, metadata)
        boundary.assert_same_system(expected, actual)
        # Simulate a reconstructed result losing a required formula and its
        # tokens. Do not disable DB immutability just to corrupt the fixture.
        missing = tmp_path / "missing-body.dempkg"
        boundary.without_formulas(actual, missing, {body_public_id})
        with pytest.raises(AssertionError, match="reconstructed system differs"):
            boundary.assert_same_system(expected, missing)
