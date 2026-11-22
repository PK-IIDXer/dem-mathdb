"""Idempotent ownership backfill for this seed's stable public identities.

Never infer ownership from names, namespaces, integer ranges or proof status.
The catalog also handles an existing workspace whose seeders return early.
"""
from functools import wraps

from sqlalchemy import select, update

from dem.db.models import (
    Axiom, AxiomSystem, Definition, InstalledRelease, Package, PackageRelease,
    Proof, ReleaseDependency, ReleaseLockEntry, Symbol, Theorem,
)
from dem.db.seeds.public_catalog import PACKAGE_ENTITIES

PACKAGES = (
    {"key": 'public-core', "name": 'dem.public.logic', "version": '1.0.0',
     "depends": (), "phase": 'public_core',
     "seed": 'dem.db.seeds:seed_public_core'},
    {"key": 'public-demo', "name": 'dem.public.demos', "version": '1.0.0',
     "depends": ('public-core',), "phase": 'public_demo',
     "seed": 'dem.db.seeds.public_demo:seed_public_demo'},
    {"key": 'public-natural-deduction', "name": 'dem.public.natural-deduction', "version": '1.0.0',
     "depends": ('public-core',), "phase": 'public_natural_deduction',
     "seed": 'dem.db.seeds.public_natural_deduction:seed_public_natural_deduction'},
    {"key": 'public-equivalence', "name": 'dem.public.equivalence', "version": '1.0.0',
     "depends": ('public-core', 'public-natural-deduction'), "phase": 'public_equivalence',
     "seed": 'dem.db.seeds.public_equivalence:seed_public_equivalence'},
    {"key": 'public-zfc', "name": 'dem.public.zfc', "version": '2.0.0',
     "depends": ('public-equivalence',), "phase": 'public_zfc',
     "seed": 'dem.db.seeds.public_zfc:seed_public_zfc'},
    {"key": 'public-mk', "name": 'dem.public.mk', "version": '2.0.0',
     "depends": ('public-zfc',), "phase": 'public_mk',
     "seed": 'dem.db.seeds.public_mk:seed_public_mk'},
    {"key": 'public-unique-existence', "name": 'dem.public.unique-existence', "version": '2.0.0',
     "depends": ('public-equivalence',), "phase": 'public_unique_existence',
     "seed": 'dem.db.seeds.public_unique_existence:seed_public_unique_existence'},
    {"key": 'public-relations', "name": 'dem.public.relations', "version": '2.0.0',
     "depends": ('public-zfc', 'public-unique-existence'), "phase": 'public_relations',
     "seed": 'dem.db.seeds.public_relations:seed_public_relations'},
    {"key": 'public-class-relations', "name": 'dem.public.class-relations', "version": '2.0.0',
     "depends": ('public-relations', 'public-mk'), "phase": 'public_class_relations',
     "seed": 'dem.db.seeds.public_class_relations:seed_public_class_relations'},
    {"key": 'public-algebra', "name": 'dem.public.algebra', "version": '1.0.0',
     "depends": ('public-relations',), "phase": 'public_algebra',
     "seed": 'dem.db.seeds.public_algebra:seed_public_algebra'},
)

VERSIONS = {package["key"]: package["version"] for package in PACKAGES}
RUNTIME_RANGE = ">=0.1.0,<0.2.0"
PACKAGE_GROUPS = tuple((package["key"], (), package["depends"]) for package in PACKAGES)


def package_name(key):
    return {package["key"]: package["name"] for package in PACKAGES}[key]

MODELS = (Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof)


def assign_public_releases(session):
    """Assign only catalogued rows; completed calls emit no writes."""
    catalogs = {model.__tablename__: {} for model in MODELS}
    expected = {key: set() for key, _, _ in PACKAGE_GROUPS}
    for phase in PACKAGE_ENTITIES.values():
        key = phase["package"]
        for kind, ids in phase["entities"].items():
            for pid in ids:
                catalogs[kind][pid] = key
                expected[key].add((kind, pid))
    present = {key: set() for key in expected}
    pending = []
    for model in MODELS:
        kind = model.__tablename__
        for row_id, pid, release_id in session.execute(select(model.id, model.public_id, model.release_id)):
            key = catalogs[kind].get(pid)
            if key is not None:
                present[key].add((kind, pid))
                pending.append((model, row_id, release_id, key))

    packages = {p.name: p for p in session.scalars(select(Package))}
    releases = {(r.package_id, r.version): r for r in session.scalars(select(PackageRelease))}
    specs = {key: deps for key, _, deps in PACKAGE_GROUPS}
    selected = {}

    def ensure(key):
        if key in selected:
            return selected[key]
        deps = {dep: ensure(dep) for dep in specs[key]}
        name = package_name(key)
        version = VERSIONS[key]
        package = packages.get(name)
        visibility = "public"
        if package is None:
            package = Package(name=name, owner="dem", visibility=visibility)
            session.add(package)
            session.flush()
            packages[name] = package
        elif package.owner != "dem" or (package.visibility != visibility and not (
            package.visibility == "private"
            and (imported := releases.get((package.id, version))) is not None
            and imported.published_at is not None
        )):
            raise ValueError(f"seed package metadata conflict: {name}")
        manifest = {"package": name, "version": version, "dem_runtime": RUNTIME_RANGE,
                    "depends": {package_name(dep): f"={row.version}" for dep, row in deps.items()}}
        release = releases.get((package.id, version))
        if release is None:
            release = PackageRelease(package_id=package.id, version=version,
                                     dem_runtime_range=RUNTIME_RANGE, manifest=manifest)
            session.add(release)
            session.flush()
            for dep in deps.values():
                session.add(ReleaseDependency(release_id=release.id, depends_package_id=dep.package_id, range=f"={dep.version}"))
            pins = {dep.id for dep in deps.values()}
            for dep in deps.values():
                pins.update(session.scalars(select(ReleaseLockEntry.locked_release_id).where(ReleaseLockEntry.release_id == dep.id)))
            for pin in sorted(pins):
                session.add(ReleaseLockEntry(release_id=release.id, locked_release_id=pin))
            session.flush()
        elif (({k: release.manifest.get(k) for k in manifest} if release.published_at is not None else
               {k: v for k, v in release.manifest.items() if k not in ("_archive_catalogs", "_archive_formula_ids")}) != manifest
              or release.dem_runtime_range != RUNTIME_RANGE):
            raise ValueError(f"seed release metadata conflict: {name}@{version}")
        selected[key] = release
        return release

    for key, rows in present.items():
        if rows:
            ensure(key)
    for model, row_id, previous, key in pending:
        target = selected[key].id
        if previous is not None and previous != target:
            raise ValueError(f"seed ownership conflict: {model.__tablename__}:{row_id}")
        if previous is None:
            values = {"release_id": target}
            # Ownership is metadata, not an edit to the mathematical statement.
            if hasattr(model, "updated_at"):
                values["updated_at"] = model.updated_at
            session.execute(update(model).where(model.id == row_id).values(**values))
    installed = set(session.scalars(select(InstalledRelease.release_id)))
    for key, release in selected.items():
        if present[key] == expected[key] and release.id not in installed:
            session.add(InstalledRelease(release_id=release.id))
    session.flush()


def seed_packages(function):
    """Run once at the outer seed boundary, including its early-return path."""
    @wraps(function)
    def wrapped(session, *args, **kwargs):
        nested = session.info.get("seed_package_boundary", False)
        session.info["seed_package_boundary"] = True
        try:
            result = function(session, *args, **kwargs)
            if not nested:
                assign_public_releases(session)
            return result
        finally:
            if nested:
                session.info["seed_package_boundary"] = True
            else:
                session.info.pop("seed_package_boundary", None)
    return wrapped
