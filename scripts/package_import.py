"""Atomic L2 release import and exact-lock reconstruction; no HTTP write path."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import io
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile, BadZipFile

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dem.db.models import (Base, Symbol, Formula, Definition, Axiom, AxiomSystem,
                           Theorem, Proof, Package, PackageRelease, ReleaseDependency,
                           ReleaseLockEntry, InstalledRelease)
from dem.db.engine import make_engine
from dem.db.seed import seed_language_catalog, seed_inference_rules
from dem.errors import DemError
from dem.services.package import dependency_closure, publish_release
from scripts.workspace_import import (_Reconstruction, _json, require, validate_rows,
                                      reconstruct_rows, WorkspaceImportError)
from webapi.workspace_export import _JSONL_EXPORTS, _iter_rows, _manifest, WorkspaceExportMetadata
from webapi.package_export import write_package_export

MODELS = dict(symbols=Symbol, formulas=Formula, definitions=Definition, axioms=Axiom,
              axiom_systems=AxiomSystem, theorems=Theorem, proofs=Proof)
RUNTIME = ("formula_types.jsonl", "symbol_types.jsonl", "inference_rules.jsonl")
NAME = re.compile(r"[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+\Z")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def _check_manifest_pins(depends, pins):
    for dep, requirement in depends.items():
        require(dep in pins and requirement == "=" + pins[dep], "manifest/lock disagreement")


def _check_no_import_records(rows):
    require(not rows["import_records.jsonl"], "External verification records are not accepted until their checks can be rerun")


def _check_dependency_version(release, version):
    require(release.version == version, "installed dependency version mismatch")


def _check_dependency_installed(session, release):
    require(session.get(InstalledRelease, release.id) is not None, "dependency is not installed")


def read_lock(value):
    if isinstance(value, (str, Path)):
        value = _json(Path(value).read_bytes())
    require(type(value) is dict and set(value) == {"schema_version", "packages"}, "invalid lock shape")
    require(type(value["schema_version"]) is int and value["schema_version"] == 1, "unsupported lock version")
    require(type(value["packages"]) is dict, "invalid lock packages")
    for name, version in value["packages"].items():
        require(type(name) is str and NAME.fullmatch(name) is not None, "invalid package name")
        require(type(version) is str and VERSION.fullmatch(version) is not None, "lock must contain exact versions")
    return dict(value["packages"])


@dataclass(frozen=True)
class ReleaseArchive:
    data: bytes
    manifest: dict
    pins: dict[str, str]
    rows: dict[str, list[dict]]


def read_release(source):
    data = Path(source).read_bytes()
    with ZipFile(io.BytesIO(data)) as archive:
        expected = {"manifest.json", "dem.lock", *(i.filename for i in _JSONL_EXPORTS)}
        names = archive.namelist()
        require(len(names) == len(set(names)) and set(names) == expected, "invalid release archive members")
        manifest = _json(archive.read("manifest.json"))
        pins = read_lock(_json(archive.read("dem.lock")))
        rows = {item.filename: [_json(line) for line in archive.read(item.filename).splitlines()]
                for item in _JSONL_EXPORTS}
    require(type(manifest) is dict, "invalid manifest")
    name, version = manifest["package"], manifest["version"]
    read_lock({"schema_version": 1, "packages": {name: version}})
    require(type(manifest["description"]) is str, "invalid description")
    depends = manifest["depends"]
    require(type(depends) is dict and name not in pins, "invalid manifest dependencies")
    # v1 installs exact locks; range resolution/upgrade is deliberately absent.
    _check_manifest_pins(depends, pins)
    expected = _manifest(WorkspaceExportMetadata(name, manifest["description"]), [])
    expected.update(version=version, depends=depends, archive_kind="package_release")
    expected["empty_field_reasons"].pop("depends", None)
    require(manifest == expected, "manifest/runtime metadata mismatch")
    _check_no_import_records(rows)
    return ReleaseArchive(data, manifest, pins, rows)


@lru_cache(maxsize=1)
def _runtime_catalog():
    # Read the runtime's own catalog through its ordinary initialization path.
    # No writes to the import destination occur during this L1 comparison.
    engine = make_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            seed_language_catalog(session)
            seed_inference_rules(session)
            return {item.filename: list(_iter_rows(session, item, frozenset()))
                    for item in _JSONL_EXPORTS if item.filename in RUNTIME}
    finally:
        engine.dispose()


def _check_installed(session, archive):
    releases = {}
    for name, version in archive.pins.items():
        matches = list(session.scalars(select(PackageRelease).join(Package)
                                      .where(Package.name == name)))
        require(len(matches) == 1, "dependency release is missing or ambiguous")
        _check_dependency_installed(session, matches[0])
        _check_dependency_version(matches[0], version)
        releases[name] = matches[0]
    return releases


def _check_single_version(session, archive):
    existing = session.scalar(select(PackageRelease.id).join(Package)
                              .where(Package.name == archive.manifest["package"]))
    require(existing is None, "package already has a release; upgrades are not supported")


def _check_lock_closure(session, archive, dependencies):
    reached = set()
    for name in archive.manifest["depends"]:
        reached.update(dependency_closure(session, dependencies[name].id))
    require(reached == {row.id for row in dependencies.values()}, "lock is not the declared dependency closure")


def _check_external_owner(obj, allowed):
    require(obj.release_id in allowed, "external reference is not owned by a locked release")


def _external_entities(session, archive, dependencies):
    allowed = {r.id for r in dependencies.values()}
    external = defaultdict(dict)
    # All potential external identities are read, never recreated or assigned.
    for table, model in MODELS.items():
        if table == "formulas":
            continue  # Shared formulas must carry their tokens in this archive.
        own = {r["public_id"] for r in archive.rows[table + ".jsonl"]}
        for obj in session.scalars(select(model)):
            require(obj.public_id not in own, "archive attempts to replace an existing entity")
            external[table][obj.public_id] = obj
    # The common reconstructor checks every public-ID reference, including
    # formula-token symbols and all columns of definition identity.
    build = _Reconstruction(session, archive.rows, external)
    references = build.reference_tables
    for filename, rows in archive.rows.items():
        for row in rows:
            for field, table in references.items():
                pid = row.get(field)
                if pid is not None and pid in external.get(table, {}):
                    _check_external_owner(external[table][pid], allowed)
    # Detail rows may only write their archive-owned parent, never a dependency.
    from dem.db.package_triggers import DETAILS
    plural = {model.__tablename__: table for table, model in MODELS.items()}
    for singular, (parent, column) in DETAILS.items():
        filename = singular + ("es" if singular.endswith("alias") else "s") + ".jsonl"
        if filename not in archive.rows or parent not in plural:
            continue
        field = column.removesuffix("_id") + "_public_id"
        for row in archive.rows[filename]:
            require(row[field] in build.maps[plural[parent]], "detail parent is not owned by this archive")
    for row in archive.rows["proofs.jsonl"]:
        require(row["theorem_public_id"] in build.maps["theorems"], "proof theorem must belong to this release")
    # Auxiliary witnesses recovered by DefinitionService may only come from
    # this release's pinned foundation, just like explicit references.
    for table, objects in external.items():
        external[table] = {pid: obj for pid, obj in objects.items() if obj.release_id in allowed}
    return build


def _preflight(session, archive):
    validate_rows(session, archive.rows)
    for filename, expected in _runtime_catalog().items():
        require(archive.rows[filename] == expected, "runtime catalog mismatch: " + filename)
    _check_single_version(session, archive)
    dependencies = _check_installed(session, archive)
    _check_lock_closure(session, archive, dependencies)
    return dependencies, _external_entities(session, archive, dependencies)


@dataclass(frozen=True)
class ReleaseImportResult:
    release_id: int
    package: str
    version: str
    content_digest: str
    l1_seconds: float
    l2_seconds: float
    write_seconds: float


def _install(session, archive):
    started = perf_counter()
    dependencies, build = _preflight(session, archive)
    l1 = perf_counter() - started
    writing = perf_counter()
    seed_language_catalog(session)
    seed_inference_rules(session)
    reconstruct_rows(session, archive.rows, build)
    # Frozen shared catalogs must describe real reconstructed rows. Checking
    # them before freezing prevents snapshots from concealing a bad parent.
    for item in _JSONL_EXPORTS:
        if item.filename in ("tags.jsonl", "namespaces.jsonl"):
            actual = {row["name"]: row for row in _iter_rows(session, item, frozenset())}
            require(all(actual.get(row["name"]) == row for row in archive.rows[item.filename]),
                    "reconstructed shared catalog mismatch: " + item.filename)
    manifest = archive.manifest
    package = session.scalar(select(Package).where(Package.name == manifest["package"]))
    if package is None:
        package = Package(name=manifest["package"], owner=manifest["package"].split(".")[0], visibility="private")
        session.add(package)
        session.flush()
    release = PackageRelease(package_id=package.id, version=manifest["version"],
                             dem_runtime_range=manifest["dem_runtime"], manifest={**manifest, "_archive_catalogs": {
                                 name: archive.rows[name] for name in ("tags.jsonl", "namespaces.jsonl")
                             }, "_archive_formula_ids": [row["public_id"] for row in archive.rows["formulas.jsonl"]]})
    session.add(release)
    session.flush()
    for table in MODELS:
        if table != "formulas":
            for obj in build.done[table].values():
                obj.release_id = release.id
    for name, requirement in manifest["depends"].items():
        session.add(ReleaseDependency(release_id=release.id, depends_package_id=dependencies[name].package_id, range=requirement))
    for dependency in dependencies.values():
        session.add(ReleaseLockEntry(release_id=release.id, locked_release_id=dependency.id))
    session.flush()
    # Exhaustive canonical read-back checks all details, status, identity,
    # shared formula metadata and runtime roles, not only owned row counts.
    with TemporaryDirectory(prefix="dem-release-") as directory:
        output = Path(directory) / "roundtrip.dempkg"
        write_package_export(session, output, release.id)
        require(output.read_bytes() == archive.data, "reconstructed release archive mismatch")
    publish_release(session, release.id)
    require(release.content_digest == hashlib.sha256(archive.data).hexdigest(), "published digest mismatch")
    session.add(InstalledRelease(release_id=release.id))
    session.flush()
    return ReleaseImportResult(release.id, package.name, release.version, release.content_digest,
                               l1, build.l2, perf_counter() - writing - build.l2)


def import_release(session: Session, source: Path):
    require(not session.in_transaction(), "import requires an idle session")
    try:
        archive = read_release(source)
        with session.begin():
            return _install(session, archive)
    except (DemError, IntegrityError, KeyError, TypeError, ValueError, BadZipFile) as exc:
        session.info.clear()
        if isinstance(exc, WorkspaceImportError):
            raise
        raise WorkspaceImportError(f"{type(exc).__name__}: {exc}") from exc


def reconstruct_lock(session: Session, lock, directory: Path):
    """Reconstruct one exact lock in an empty migrated DB, atomically as a whole."""
    require(not session.in_transaction(), "reconstruction requires an idle session")
    pins = read_lock(lock)
    archives = {}
    for path in sorted(Path(directory).glob("*.dempkg")):
        archive = read_release(path)
        name, version = archive.manifest["package"], archive.manifest["version"]
        if pins.get(name) == version:
            require(name not in archives, "duplicate release archive")
            archives[name] = archive
    require(set(archives) == set(pins), "lock archives are missing")
    order, active = [], set()
    def visit(name):
        require(name not in active, "cyclic lock")
        if name in order:
            return
        active.add(name)
        for dep, version in archives[name].pins.items():
            require(pins.get(dep) == version, "reconstruction lock disagrees with release lock")
            visit(dep)
        active.remove(name)
        order.append(name)
    for name in sorted(pins):
        visit(name)
    try:
        with session.begin():
            for table in Base.metadata.sorted_tables:
                require(session.execute(select(table).limit(1)).first() is None, "reconstruction destination is not empty")
            return [_install(session, archives[name]) for name in order]
    except (DemError, IntegrityError, KeyError, TypeError, ValueError) as exc:
        session.info.clear()
        if isinstance(exc, WorkspaceImportError):
            raise
        raise WorkspaceImportError(f"{type(exc).__name__}: {exc}") from exc
