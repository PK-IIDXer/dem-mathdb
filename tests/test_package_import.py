"""Release L1 rejection, L2 reconstruction and atomicity on both dialects."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_workspace_import import engines
from dem.db.models import (Base, Symbol, Formula, Definition, Axiom, AxiomSystem, Theorem, Proof,
                           Package, PackageRelease, ReleaseDependency, ReleaseLockEntry, InstalledRelease)
from dem.db.seed import seed_language, seed_inference_rules
from dem.services.symbol import SymbolService
from dem.services.formula import FormulaService
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService
from dem.services.theorem import TheoremService
from dem.services.proof import ProofService
from dem.types import Token, SymbolTypeName, AxiomStepInput, TheoremStepInput, LogicalDefinitionInput
from scripts.package_import import import_release, reconstruct_lock
import scripts.package_import as importer
from scripts.workspace_import import WorkspaceImportError
from webapi.package_export import write_package_export
from webapi.workspace_export import write_workspace_export, WorkspaceExportMetadata, _zip_info, _json_bytes


@pytest.fixture
def releases(tmp_path, engines):
    engine = engines()
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        symbols = SymbolService(session)
        x = symbols.register("x", symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value).id, 0)
        eq = symbols.get_by_role("equality")
        phi = symbols.register("phi", symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id, 0)
        body = FormulaService(session).register([Token(symbol_id=phi.id)])
        formula = FormulaService(session).register([Token(symbol_id=eq.id), Token(symbol_id=x.id), Token(symbol_id=x.id)])
        axiom = AxiomService(session).register("basis", formula.id)
        theorem = TheoremService(session).register("basis", formula.id)
        proofs = ProofService(session)
        proof = proofs.create_proof(theorem.id)
        proofs.add_step(proof.id, AxiomStepInput(axiom.id))
        proofs.validate(proof.id)
        package = Package(name="example.base", owner="example", visibility="private")
        session.add(package)
        session.flush()
        base = PackageRelease(package_id=package.id, version="1.0.0", dem_runtime_range=">=0.1.0,<0.2.0", manifest={})
        session.add(base)
        session.flush()
        for model in (Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof):
            session.execute(update(model).values(release_id=base.id))
        second = TheoremService(session).register("dependent", formula.id)
        second_proof = proofs.create_proof(second.id)
        proofs.add_step(second_proof.id, TheoremStepInput(proof.id))
        proofs.validate(second_proof.id)
        definition = DefinitionService(session).register(LogicalDefinitionInput("wrap", (phi.id,), body.id))
        package2 = Package(name="example.leaf", owner="example", visibility="private")
        session.add(package2)
        session.flush()
        leaf = PackageRelease(package_id=package2.id, version="1.0.0", dem_runtime_range=base.dem_runtime_range, manifest={})
        session.add(leaf)
        session.flush()
        second.release_id = second_proof.release_id = leaf.id
        definition.release_id = definition.new_symbol.release_id = leaf.id
        DefinitionService(session).get_axiom(definition.id).release_id = leaf.id
        session.add(ReleaseDependency(release_id=leaf.id, depends_package_id=package.id, range="=1.0.0"))
        session.add(ReleaseLockEntry(release_id=leaf.id, locked_release_id=base.id))
        session.commit()
        directory = tmp_path / "archives"
        paths = [directory / "base.dempkg", directory / "leaf.dempkg"]
        write_package_export(session, paths[0], base.id)
        write_package_export(session, paths[1], leaf.id)
        whole = tmp_path / "whole.dempkg"
        metadata = WorkspaceExportMetadata("example.whole", "test")
        write_workspace_export(session, whole, metadata)
    return paths, whole, metadata


def test_two_reconstructions_match(releases, engines, tmp_path):
    paths, whole, metadata = releases
    lock = {"schema_version": 1, "packages": {"example.base": "1.0.0", "example.leaf": "1.0.0"}}
    for run in range(2):
        with Session(engines()) as session:
            results = reconstruct_lock(session, lock, paths[0].parent)
            assert len(results) == 2
            assert all(row.published_at and row.content_digest for row in session.scalars(select(PackageRelease)))
            for source, result in zip(paths, results):
                target = tmp_path / f"{run}-{result.package}.dempkg"
                write_package_export(session, target, result.release_id)
                assert source.read_bytes() == target.read_bytes()
            target = tmp_path / f"whole-{run}.dempkg"
            write_workspace_export(session, target, metadata)
            assert target.read_bytes() == whole.read_bytes()
            # This body is an implicit definition input, not a direct FK target.
            body = session.scalar(select(Formula).where(Formula.token_count == 1))
            assert body is not None
            with pytest.raises(IntegrityError, match="published_formula_update"):
                with session.begin_nested():
                    session.execute(update(Formula).where(Formula.id == body.id).values(description="tampered"))


def tamper(source, destination, change):
    with ZipFile(source) as archive:
        data = {name: (json.loads(archive.read(name)) if name in ("manifest.json", "dem.lock")
                       else [json.loads(line) for line in archive.read(name).splitlines()])
                for name in archive.namelist()}
    change(data)
    with ZipFile(destination, "w") as archive:
        for name, rows in data.items():
            content = _json_bytes(rows) if name in ("manifest.json", "dem.lock") else b"".join(_json_bytes(row) for row in rows)
            archive.writestr(_zip_info(name), content)
    return destination


def snapshot(session):
    return {table.name: [tuple(row) for row in session.execute(select(table))]
            for table in Base.metadata.sorted_tables}


@pytest.mark.parametrize("case", ["missing_dependency", "uninstalled", "version", "second_version", "missing_entity",
                                 "wrong_owner", "null_owner", "manifest_lock", "extra_pin", "import_record",
                                 "step", "status", "hash", "runtime", "lock_shape", "manifest_shape", "namespace"])
def test_rejections_are_atomic(case, releases, engines, tmp_path):
    paths, _, _ = releases
    engine = engines()
    with Session(engine) as session:
        if case != "missing_dependency":
            import_release(session, paths[0])
        source = paths[1]
        if case == "uninstalled":
            session.delete(session.scalar(select(InstalledRelease)))
            session.commit()
        if case == "second_version":
            source = tamper(paths[0], tmp_path / "bad.dempkg", lambda data: data["manifest.json"].update(version="2.0.0"))
        elif case == "version":
            def change(data):
                data["dem.lock"]["packages"]["example.base"] = "2.0.0"
                data["manifest.json"]["depends"]["example.base"] = "=2.0.0"
            source = tamper(source, tmp_path / "bad.dempkg", change)
        elif case == "manifest_lock":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["manifest.json"]["depends"].update({"example.base": "=9.0.0"}))
        elif case == "extra_pin":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["manifest.json"].update(depends={}))
        elif case == "missing_entity":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["proof_steps.jsonl"][0].update(applied_proof_public_id="00000000-0000-4000-8000-000000000001"))
        elif case in ("wrong_owner", "null_owner"):
            # Model a pre-existing workspace with invalid ownership using a
            # separately created draft entity, never unpublish an imported one.
            symbols = SymbolService(session)
            alien = symbols.register("alien", symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value).id, 0)
            if case == "wrong_owner":
                package = Package(name="example.other", owner="example", visibility="private")
                session.add(package)
                session.flush()
                release = PackageRelease(package_id=package.id, version="1.0.0", dem_runtime_range=">=0.1.0,<0.2.0", manifest={})
                session.add(release)
                session.flush()
                alien.release_id = release.id
            pid = alien.public_id
            session.commit()
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["formula_tokens.jsonl"][1].update(symbol_public_id=pid))
        elif case == "import_record":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["import_records.jsonl"].append({"forged": True}))
        elif case == "step":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["proof_steps.jsonl"][0].update(step_kind="premise", premise_ord=99, applied_proof_public_id=None))
        elif case == "status":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["theorems.jsonl"][0].update(status="conjecture"))
        elif case == "hash":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["formulas.jsonl"][0].update(hash="0" * 64))
        elif case == "runtime":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["inference_rules.jsonl"][0].update(remarks="changed"))
        elif case == "lock_shape":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["dem.lock"].update(schema_version=True))
        elif case == "manifest_shape":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["manifest.json"].update(unrecognized=True))
        elif case == "namespace":
            source = tamper(source, tmp_path / "bad.dempkg", lambda data: data["namespaces.jsonl"][0].update(parent="invalid.parent"))
        before = snapshot(session)
        session.rollback()
        writes = []
        def record(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                writes.append(statement)
        event.listen(engine, "before_cursor_execute", record)
        try:
            messages = {"second_version": "package already has a release",
                        "null_owner": "external reference is not owned by a locked release",
                        "wrong_owner": "external reference is not owned by a locked release",
                        "version": "installed dependency version mismatch",
                        "uninstalled": "dependency is not installed",
                        "manifest_lock": "manifest/lock disagreement",
                        "import_record": "External verification records"}
            with pytest.raises(WorkspaceImportError, match=messages.get(case)):
                import_release(session, source)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        if case not in ("step", "status", "hash", "namespace"):
            assert writes == []
        assert snapshot(session) == before


@pytest.mark.parametrize("guard,case", [("_check_single_version", "second_version"),
                                       ("_check_dependency_installed", "uninstalled"),
                                       ("_check_dependency_version", "version"),
                                       ("_check_manifest_pins", "manifest_lock"),
                                       ("_check_no_import_records", "import_record"),
                                       ("_check_lock_closure", "extra_pin"),
                                       ("_check_external_owner", "null_owner")])
def test_preflight_guard_mutations_fail_no_write_assertion(guard, case, releases, engines, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, guard, lambda *args: None)
    # The normal rejection contract includes no attempted destination writes.
    # A later FK/closure/read-back guard must not hide a missing L1 guard.
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        test_rejections_are_atomic(case, releases, engines, tmp_path)


@pytest.mark.parametrize("case,prefix", [("missing_entity", "missing reference:"),
                                       ("runtime", "runtime catalog mismatch:"),
                                       ("lock_shape", "unsupported lock version"),
                                       ("manifest_shape", "manifest/runtime metadata mismatch")])
def test_remaining_preflight_guard_mutations(case, prefix, releases, engines, tmp_path, monkeypatch):
    import scripts.workspace_import as shared
    original = shared.require
    def weakened(condition, message):
        if not message.startswith(prefix):
            original(condition, message)
    monkeypatch.setattr(importer, "require", weakened)
    monkeypatch.setattr(shared, "require", weakened)
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        test_rejections_are_atomic(case, releases, engines, tmp_path)


def test_cli_install_reconstruct_and_prepare(releases, tmp_path, monkeypatch):
    from scripts.import_packages import main
    from dem.db.engine import make_engine
    paths, whole, metadata = releases
    lock = tmp_path / "dem.lock"
    lock.write_text(json.dumps({"schema_version": 1, "packages": {
        "example.base": "1.0.0", "example.leaf": "1.0.0"}}), encoding="utf-8")
    for mode in ("install", "reconstruct"):
        database = tmp_path / (mode + ".db")
        url = "sqlite:///" + database.as_posix()
        report = tmp_path / (mode + ".json")
        sources = paths if mode == "install" else [lock]
        for source in sources:
            arguments = ["import_packages", mode, str(source), "--database-url", url,
                         "--report", str(report), "--archives", str(paths[0].parent)]
            monkeypatch.setattr("sys.argv", arguments + ["--prepare-only"])
            main()
            monkeypatch.setattr("sys.argv", arguments)
            main()
            assert json.loads(report.read_text(encoding="utf-8"))["status"] == "passed"
        engine = make_engine(url)
        try:
            with Session(engine) as session:
                output = tmp_path / (mode + ".dempkg")
                write_workspace_export(session, output, metadata)
                assert output.read_bytes() == whole.read_bytes()
        finally:
            engine.dispose()


def test_later_release_failure_rolls_back_entire_lock(releases, engines, tmp_path):
    paths, _, _ = releases
    directory = tmp_path / "broken-lock"
    directory.mkdir()
    (directory / "base.dempkg").write_bytes(paths[0].read_bytes())
    tamper(paths[1], directory / "leaf.dempkg",
           lambda data: data["theorems.jsonl"][0].update(status="conjecture"))
    lock = {"schema_version": 1, "packages": {"example.base": "1.0.0", "example.leaf": "1.0.0"}}
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError, match="status mismatch"):
            reconstruct_lock(session, lock, directory)
        assert all(not rows for rows in snapshot(session).values())


def test_all_definition_kinds_across_release_boundary(tmp_path, engines, monkeypatch):
    import test_workspace_import as workspace_tests
    original = workspace_tests.write_workspace_export
    archives = tmp_path / "definition-releases"
    def capture(session, destination, metadata):
        result = original(session, destination, metadata)
        if archives.exists():
            return result
        releases = []
        for name in ("example.variables", "example.definitions"):
            package = Package(name=name, owner="example", visibility="private")
            session.add(package)
            session.flush()
            release = PackageRelease(package_id=package.id, version="1.0.0",
                                     dem_runtime_range=">=0.1.0,<0.2.0", manifest={})
            session.add(release)
            session.flush()
            releases.append(release)
        base, leaf = releases
        session.execute(update(Symbol).values(release_id=base.id))
        for model in (Definition, Axiom, AxiomSystem, Theorem, Proof):
            session.execute(update(model).values(release_id=leaf.id))
        session.execute(update(Symbol).where(Symbol.id.in_(select(Definition.new_symbol_id))).values(release_id=leaf.id))
        session.add(ReleaseDependency(release_id=leaf.id, depends_package_id=base.package_id, range="=1.0.0"))
        session.add(ReleaseLockEntry(release_id=leaf.id, locked_release_id=base.id))
        session.flush()
        for release in releases:
            name = session.get(Package, release.package_id).name
            write_package_export(session, archives / (name + ".dempkg"), release.id)
        return result
    # Reuse the ordinary service-built, all-kinds fixture and its original L2
    # roundtrip assertions. Only capture an additional distribution of it.
    monkeypatch.setattr(workspace_tests, "write_workspace_export", capture)
    workspace_tests.test_definition_kinds_birth_identity_and_ordinal_gaps(tmp_path, engines)
    lock = {"schema_version": 1, "packages": {"example.variables": "1.0.0", "example.definitions": "1.0.0"}}
    with Session(engines()) as session:
        results = reconstruct_lock(session, lock, archives)
        for result in results:
            output = tmp_path / (result.package + ".dempkg")
            write_package_export(session, output, result.release_id)
            assert output.read_bytes() == (archives / output.name).read_bytes()
