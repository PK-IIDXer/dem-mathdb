"""Distribution reference closure, independent of proof validation and status."""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import and_, select, union

from dem.db.models import Base, PackageRelease, ReleaseDependency, ReleaseLockEntry

ENTITY_TABLES = ("symbol", "definition", "axiom", "axiom_system", "theorem", "proof")
# Detail rows travel with their parent. Formulas are shared values, not owned.
DETAIL_OWNERS = {
    "definition_formal_param": ("definition", "definition_id"),
    "axiom_system_member": ("axiom_system", "axiom_system_id"),
    "theorem_premise": ("theorem", "theorem_id"),
    "proof_step": ("proof", "proof_id"),
    "proof_step_subst_term": ("proof", "proof_id"),
    "proof_step_subst_prop": ("proof", "proof_id"),
    "proof_step_subst_prop_param": ("proof", "proof_id"),
}


def _references():
    tables = Base.metadata.tables
    for name in (*ENTITY_TABLES, *DETAIL_OWNERS):
        table = tables[name]
        if name in DETAIL_OWNERS:
            parent, column = DETAIL_OWNERS[name]
            owner = tables[parent]
            source = table.join(owner, table.c[column] == owner.c.id)
        else:
            owner, source = table, table
        for constraint in sorted(table.foreign_key_constraints, key=lambda fk: str(fk.name)):
            target = constraint.referred_table
            if target.name in (*ENTITY_TABLES, "formula"):
                yield name, constraint, owner, source, target


def _reference_join(constraint, target):
    """Preserve every local/remote column pair, including composite identities."""
    return and_(*(target.c[fk.column.name] == fk.parent for fk in constraint.elements))


def _reference_name(name, constraint):
    columns = ",".join(fk.parent.name for fk in constraint.elements)
    return f"{name}.{columns}"


def release_formula_ids(release_id):
    """SQL set of every formula directly used by an owned entity or detail."""
    queries = [select(target.c.id.label("id")).select_from(source.join(target, _reference_join(constraint, target))).where(owner.c.release_id == release_id)
               for _, constraint, owner, source, target in _references() if target.name == "formula"]
    return union(*queries)


def _dependency_references():
    """The actual joins checked by closure and exercised by corpus coverage."""
    tables = Base.metadata.tables
    token = tables["formula_token"]
    for name, constraint, owner, source, target in _references():
        reason = _reference_name(name, constraint)
        if target.name == "formula":
            source = source.join(target, _reference_join(constraint, target)).join(
                token, token.c.formula_id == target.c.id
            )
            yield reason + ":symbol", owner, source, tables["symbol"], lambda dest: dest.c.id == token.c.symbol_id
        else:
            yield reason, owner, source, target, partial(_reference_join, constraint)
    symbol, definition, axiom = (tables[n] for n in ("symbol", "definition", "axiom"))
    # A symbol's definition and its defining axiom are part of its meaning.
    yield "symbol.definition", symbol, symbol, definition, lambda dest: dest.c.new_symbol_id == symbol.c.id
    yield "definition.axiom", definition, definition, axiom, lambda dest: dest.c.definition_id == definition.c.id


def dependency_closure(session, release_id: int) -> set[int]:
    """Resolve declarations through this release's build pins, never installed state.

    A lock must pin exactly the declared transitive closure, one version per
    package. Missing pins, undeclared pins and cycles fail closed.
    """
    root = session.get(PackageRelease, release_id)
    if root is None:
        raise ValueError("unknown release")
    pins = list(session.scalars(select(PackageRelease).join(ReleaseLockEntry, ReleaseLockEntry.locked_release_id == PackageRelease.id).where(ReleaseLockEntry.release_id == release_id)))
    by_package = {p.package_id: p for p in pins}
    if len(by_package) != len(pins) or root.package_id in by_package:
        raise ValueError("lock has conflicting versions or self pin")
    reached, active = set(), set()

    def visit(release):
        if release.id in active:
            raise ValueError("cyclic release dependencies")
        if release.id in reached:
            return
        active.add(release.id)
        for package_id in session.scalars(select(ReleaseDependency.depends_package_id).where(ReleaseDependency.release_id == release.id)):
            if package_id not in by_package:
                raise ValueError("missing exact dependency pin")
            visit(by_package[package_id])
        active.remove(release.id)
        reached.add(release.id)

    visit(root)
    if reached != {release_id, *(pin.id for pin in pins)}:
        raise ValueError("lock contains undeclared dependencies")
    return reached


@dataclass(frozen=True, order=True)
class DependencyViolation:
    source_kind: str
    source_public_id: str
    reference: str
    target_kind: str
    target_public_id: str
    target_release_id: int | None


def check_release_dependencies(session, release_id: int) -> list[DependencyViolation]:
    """Return references outside the release's declared, exactly pinned closure.

    Includes all symbol references in formulas, substitutions and parameters,
    pinned proofs, their theorems, defining axioms and axiom-system members.
    NULL ownership is external too; it is never a wildcard permission.
    """
    allowed = dependency_closure(session, release_id)
    violations = set()

    def collect(owner, source, target, predicate, reason):
        target = target.alias("dependency_target")
        query = select(owner.c.public_id, target.c.public_id, target.c.release_id).select_from(source.join(target, predicate(target))).where(
            owner.c.release_id == release_id,
            (target.c.release_id.is_(None) | target.c.release_id.not_in(allowed)),
        ).distinct()
        for src, dst, release in session.execute(query):
            violations.add(DependencyViolation(owner.name, src, reason, target.original.name, dst, release))

    for reason, owner, source, target, predicate in _dependency_references():
        collect(owner, source, target, predicate, reason)
    return sorted(violations)


def publish_release(session, release_id: int):
    """Freeze a release and its deterministic archive digest; caller commits."""
    from webapi.package_export import write_package_export
    from dem.services.formula import flush_pending_symbol_usage_counts
    flush_pending_symbol_usage_counts(session)
    release = session.scalar(select(PackageRelease).where(PackageRelease.id == release_id).with_for_update())
    if release is None:
        raise ValueError("unknown release")
    if release.published_at is None and "_archive_catalogs" not in release.manifest:
        from webapi.workspace_export import _JSONL_EXPORTS, _iter_rows
        release.manifest = {**release.manifest, "_archive_catalogs": {
            item.filename: list(_iter_rows(session, item, frozenset()))
            for item in _JSONL_EXPORTS if item.filename in ("tags.jsonl", "namespaces.jsonl")
        }}
        session.flush()
    if release.published_at is None and "_archive_formula_ids" not in release.manifest:
        from dem.db.models import Formula
        from dem.services.definition_archive import definition_body_formula_ids
        ids = set(session.scalars(release_formula_ids(release.id)))
        ids.update(definition_body_formula_ids(session, release.id))
        release.manifest = {**release.manifest, "_archive_formula_ids": sorted(session.scalars(
            select(Formula.public_id).where(Formula.id.in_(ids))))}
        session.flush()
    with TemporaryDirectory(prefix="dem-publish-") as directory:
        path = Path(directory) / "release.dempkg"
        write_package_export(session, path, release_id)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if release.published_at is not None:
        if release.content_digest != digest:
            raise ValueError("published release digest mismatch")
        return release
    release.content_digest = digest
    release.published_at = datetime.now(timezone.utc)
    session.flush()
    return release
