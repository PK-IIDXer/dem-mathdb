"""Deterministic single-release archives; dependency content is never bundled."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from sqlalchemy import select

from dem.db.models import Formula, Package, PackageRelease, ReleaseDependency, ReleaseLockEntry
from dem.services.package import check_release_dependencies, release_formula_ids
from dem.services.definition_archive import definition_body_formula_ids
from webapi.workspace_export import (
    WorkspaceExportMetadata, WorkspaceExportResult, _JSONL_EXPORTS, _iter_rows,
    _json_bytes, _manifest, _zip_info,
)

# SQL aliases in the shared projections. Only these owned rows are selected;
# foreign-key joins still resolve dependency public IDs without exporting them.
_OWNERS = {
    "symbols": "s", "symbol_aliases": "s", "definitions": "d",
    "definition_formal_params": "d", "axioms": "a", "axiom_systems": "system",
    "axiom_system_members": "system", "theorems": "theorem",
    "theorem_premises": "theorem", "theorem_tags": "theorem",
    "proof_identity_sequences": "theorem", "import_records": "theorem",
    "proofs": "proof", "proof_steps": "proof", "proof_step_args": "proof",
    "proof_step_subst_terms": "proof", "proof_step_subst_props": "proof",
    "proof_step_subst_prop_params": "proof",
}


def _release_exports(session, release_id, formula_public_ids=None):
    # Integer literal comes from a loaded DB row, never user SQL.
    release_id = int(release_id)
    formulas = str(release_formula_ids(release_id).compile(dialect=session.get_bind().dialect, compile_kwargs={"literal_binds": True}))
    if formula_public_ids is None:
        body_ids = definition_body_formula_ids(session, release_id)
        extra = " OR f.id IN (" + ",".join(str(i) for i in sorted(body_ids)) + ")" if body_ids else ""
        formula_condition = f"(f.id IN ({formulas}){extra})"
    else:
        query = select(Formula.id).where(Formula.public_id.in_(formula_public_ids))
        formula_condition = "f.id IN (" + str(query.compile(dialect=session.get_bind().dialect, compile_kwargs={"literal_binds": True})) + ")"
    for item in _JSONL_EXPORTS:
        name = item.filename.removesuffix(".jsonl")
        if name in _OWNERS:
            condition = f"{_OWNERS[name]}.release_id = {release_id}"
        elif name in ("formulas", "formula_tokens"):
            condition = formula_condition
        elif name == "tags":
            condition = None  # Shared catalog includes unattached display labels.
        elif name == "namespaces":
            # Ancestors are structural namespace data, not mathematical entities.
            condition = None
        elif name in ("formula_types", "symbol_types", "inference_rules", "symbol_roles"):
            condition = None  # runtime catalog (roles contain references only)
        else:
            raise ValueError(f"unclassified release export member: {name}")
        if condition:
            head, order = item.query.rsplit("ORDER BY", 1)
            head += (" AND " if "\n        WHERE " in head else " WHERE ") + condition + "\n"
            item = replace(item, query=head + "ORDER BY" + order)
        yield item


def write_package_export(session, destination: Path, release_id: int) -> WorkspaceExportResult:
    release = session.get(PackageRelease, release_id)
    if release is None:
        raise ValueError("unknown release")
    violations = check_release_dependencies(session, release.id)
    if violations:
        raise ValueError(f"undeclared release references: {violations[:10]}")
    package = session.get(Package, release.package_id)
    depends = dict(session.execute(select(Package.name, ReleaseDependency.range).join(ReleaseDependency, ReleaseDependency.depends_package_id == Package.id).where(ReleaseDependency.release_id == release.id)).all())
    manifest = _manifest(WorkspaceExportMetadata(package.name, release.manifest.get("description", "")), [])
    manifest.update(release.manifest)
    catalogs = manifest.pop("_archive_catalogs", {})
    formula_public_ids = manifest.pop("_archive_formula_ids", None)
    manifest.update(package=package.name, version=release.version, depends=depends, dem_runtime=release.dem_runtime_range, archive_kind="package_release")
    manifest["empty_field_reasons"].pop("depends", None)
    pins = dict(session.execute(select(Package.name, PackageRelease.version).join(PackageRelease, PackageRelease.package_id == Package.id).join(ReleaseLockEntry, ReleaseLockEntry.locked_release_id == PackageRelease.id).where(ReleaseLockEntry.release_id == release.id)).all())
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.writestr(_zip_info("manifest.json"), _json_bytes(manifest))
        archive.writestr(_zip_info("dem.lock"), _json_bytes({"schema_version": 1, "packages": pins}))
        for item in _release_exports(session, release.id, formula_public_ids):
            count = 0
            with archive.open(_zip_info(item.filename), "w", force_zip64=True) as member:
                records = catalogs.get(item.filename)
                if records is None:
                    records = _iter_rows(session, item, frozenset())
                for record in records:
                    member.write(_json_bytes(record))
                    count += 1
            counts[item.filename] = count
    return WorkspaceExportResult(destination, counts)
