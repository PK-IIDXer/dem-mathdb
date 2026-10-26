"""Test oracle for the entity-and-referenced-formula system boundary."""
import json
from zipfile import ZipFile, ZIP_DEFLATED

from sqlalchemy import and_, select

from dem.db.models import Base, Definition, Formula
from dem.services.definition_archive import definition_body_formula_ids
from webapi.workspace_export import _zip_info


def _formula_constraints():
    for table in Base.metadata.sorted_tables:
        if table.name == "formula_token":
            continue  # A value's own tokens do not make it part of the system.
        for constraint in table.foreign_key_constraints:
            if constraint.referred_table.name == "formula":
                yield table, constraint


def _joined_formula_ids(session, table, constraint):
    formula = Formula.__table__
    predicate = and_(*(formula.c[fk.column.name] == fk.parent
                       for fk in constraint.elements))
    return set(session.scalars(select(formula.c.id).select_from(table.join(formula, predicate))))


def _definition_bodies(session):
    for release in session.scalars(select(Definition.release_id).distinct()):
        yield from definition_body_formula_ids(session, release)


def _reference_groups(session):
    for table, constraint in _formula_constraints():
        yield str(constraint.name), _joined_formula_ids(session, table, constraint)
    yield "definition bodies", set(_definition_bodies(session))


def orphan_formula_public_ids(session):
    """The sole exclusion decision; verify candidates independently of its union."""
    formulas = dict(session.execute(select(Formula.id, Formula.public_id)).all())
    referenced = set().union(*(ids for _, ids in _reference_groups(session)))
    excluded = formulas.keys() - referenced
    # Recheck each source, not the union used to choose candidates. A mutation
    # dropping one reference group must not bless required values as orphans.
    for table, constraint in _formula_constraints():
        assert excluded.isdisjoint(_joined_formula_ids(session, table, constraint)), (
            "excluded formula has a foreign-key reference", table.name, constraint.name)
    assert excluded.isdisjoint(_definition_bodies(session)), "excluded definition body"
    return frozenset(formulas[key] for key in excluded)


def without_formulas(source, destination, excluded):
    """Keep the export format, ordering and every non-formula byte unchanged."""
    counts = {"formulas.jsonl": 0, "formula_tokens.jsonl": 0}
    with ZipFile(source) as incoming, ZipFile(
        destination, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True
    ) as outgoing:
        for name in incoming.namelist():
            if not name.endswith(".jsonl"):
                outgoing.writestr(_zip_info(name), incoming.read(name))
                continue
            field = {"formulas.jsonl": "public_id",
                     "formula_tokens.jsonl": "formula_public_id"}.get(name)
            with incoming.open(name) as rows, outgoing.open(
                _zip_info(name), "w", force_zip64=True
            ) as target:
                for line in rows:
                    if field and json.loads(line)[field] in excluded:
                        counts[name] += 1
                    else:
                        target.write(line)
    assert counts["formulas.jsonl"] == len(excluded)
    return counts


def assert_same_system(expected, rebuilt):
    assert rebuilt.read_bytes() == expected.read_bytes(), "reconstructed system differs"
