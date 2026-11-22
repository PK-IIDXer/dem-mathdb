"""Package metadata checks: no database, seed execution or snapshot fixture."""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

from dem.db.seeds import public_packages
from scripts.package_import import NAME, VERSION


def test_module_requires_no_database_fixtures():
    for name, value in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(value):
            assert set(inspect.signature(value).parameters) <= {"monkeypatch"}, name
        fixture = getattr(value, "_fixture_function_marker", None)
        if fixture is None:
            fixture = getattr(value, "_pytestfixturefunction", None)
        assert fixture is None or not fixture.autouse, name
    marks = globals().get("pytestmark", ())
    if not isinstance(marks, (list, tuple)):
        marks = (marks,)
    assert all(mark.name != "usefixtures" for mark in marks)


def _phase_entries():
    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    registry = next(
        node.value for node in ast.parse(source).body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and node.target.id == "_PHASES"
    )
    assert isinstance(registry, ast.Tuple)
    return [(ast.literal_eval(item.elts[0]), item.elts[1].id) for item in registry.elts]


def test_keys_names_and_phases_are_unique():
    for field in ("key", "name", "phase"):
        values = [package[field] for package in public_packages.PACKAGES]
        assert len(values) == len(set(values)), field


def test_names_and_versions_match_importer_grammar():
    for package in public_packages.PACKAGES:
        assert NAME.fullmatch(package["name"]), package["name"]
        assert VERSION.fullmatch(package["version"]), package["version"]


def test_dependencies_exist_are_acyclic_and_precede_dependents():
    packages = public_packages.PACKAGES
    by_key = {package["key"]: package for package in packages}
    positions = {package["key"]: i for i, package in enumerate(packages)}
    active, visited = set(), set()

    def visit(key):
        assert key in by_key, ("unknown dependency", key)
        assert key not in active, ("dependency cycle", key)
        if key in visited:
            return
        active.add(key)
        for dependency in by_key[key]["depends"]:
            visit(dependency)
        active.remove(key)
        visited.add(key)

    for package in packages:
        visit(package["key"])
    for package in packages:
        for dependency in package["depends"]:
            assert positions[dependency] < positions[package["key"]]


def test_catalog_phases_owners_and_order_match_table():
    catalog = public_packages.PACKAGE_ENTITIES
    assert list(catalog) == [package["phase"] for package in public_packages.PACKAGES]
    for package in public_packages.PACKAGES:
        assert catalog[package["phase"]]["package"] == package["key"]


def test_snapshot_phases_are_declared_in_table():
    phases = {package["phase"] for package in public_packages.PACKAGES}
    assert {phase for phase, _ in _phase_entries()} <= phases


def test_seed_entries_resolve_to_callables():
    for package in public_packages.PACKAGES:
        module, function = package["seed"].split(":")
        assert callable(getattr(importlib.import_module(module), function))


def test_compatibility_views_and_mutable_versions(monkeypatch):
    packages = public_packages.PACKAGES
    assert isinstance(public_packages.VERSIONS, dict)
    assert public_packages.VERSIONS == {row["key"]: row["version"] for row in packages}
    assert public_packages.PACKAGE_GROUPS == tuple((row["key"], (), row["depends"]) for row in packages)
    for row in packages:
        assert public_packages.package_name(row["key"]) == row["name"]
    with pytest.raises(KeyError):
        public_packages.package_name("unknown-package")
    monkeypatch.setitem(public_packages.VERSIONS, packages[0]["key"], "99.0.0")
    assert public_packages.VERSIONS[packages[0]["key"]] == "99.0.0"


def test_cascade_calls_dependencies_before_each_seed(monkeypatch):
    # Replace only the atomic seeds and metadata/display hooks. The cascade
    # functions themselves run unchanged; no proof validation is exercised here.
    import dem.db.seeds as seeds
    from dem.db.seeds import _notation

    called = set()

    def record(package):
        def seed(session):
            assert session is None
            if package["key"] not in called:
                assert set(package["depends"]) <= called, package["key"]
            called.add(package["key"])
            return seeds.PublicSeedSummary((), ())
        return seed

    for package in public_packages.PACKAGES:
        module, function = package["seed"].split(":")
        monkeypatch.setattr(importlib.import_module(module), function, record(package))
    monkeypatch.setattr(public_packages, "assign_public_releases", lambda session: None)
    monkeypatch.setattr(_notation, "validate_display_shapes", lambda session: None)
    for phase, function in _phase_entries():
        called.clear()
        getattr(seeds, function)(None)
        expected = next(row["key"] for row in public_packages.PACKAGES if row["phase"] == phase)
        assert expected in called
    called.clear()
    seeds.seed_all(None)
    assert called == {package["key"] for package in public_packages.PACKAGES}
