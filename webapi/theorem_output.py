"""Display-only projection of imported provenance onto theorem responses."""

from __future__ import annotations

import json
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models import ImportRecord
from dem.db.models.theorem import Theorem
from webapi.schemas import AxiomComparisonOut, ExternalCheckOut, ExternalSourceOut, TheoremOut


def _external_check(record: ImportRecord) -> ExternalCheckOut:
    axioms = json.loads(record.source_axioms)
    if not isinstance(axioms, list) or not all(isinstance(item, str) for item in axioms):
        raise ValueError("ImportRecord.source_axioms must be a JSON array of strings")
    comparison = (
        None
        if record.axiom_comparison is None
        else AxiomComparisonOut.model_validate_json(record.axiom_comparison)
    )
    return ExternalCheckOut(
        source_system=record.source_system,
        library=record.library,
        library_version=record.library_version,
        library_commit=record.library_commit,
        declaration=record.declaration,
        module=record.module,
        file=record.file,
        line=record.line,
        check_model=record.check_model,
        check_roundtrip=record.check_roundtrip,
        check_toolchain=record.check_toolchain,
        checked_at=record.checked_at,
        license=record.license,
        copyright=record.copyright,
        authors=record.authors,
        upstream_origin=record.upstream_origin,
        source_axioms=axioms,
        axiom_comparison=comparison,
    )


def theorem_outputs(session: Session, theorems: Iterable[Theorem]) -> list[TheoremOut]:
    items = list(theorems)
    theorem_ids = [item.id for item in items]
    grouped: dict[int, list[ExternalCheckOut]] = {theorem_id: [] for theorem_id in theorem_ids}
    if theorem_ids:
        records = session.scalars(
            select(ImportRecord)
            .where(ImportRecord.theorem_id.in_(theorem_ids))
            .order_by(ImportRecord.theorem_id, ImportRecord.id)
        )
        for record in records:
            grouped[record.theorem_id].append(_external_check(record))
    return [
        TheoremOut.model_validate(theorem, from_attributes=True).model_copy(
            update={"external_checks": grouped[theorem.id]}
        )
        for theorem in items
    ]


def theorem_output(session: Session, theorem: Theorem) -> TheoremOut:
    return theorem_outputs(session, [theorem])[0]


def external_sources(session: Session) -> list[ExternalSourceOut]:
    records = list(session.scalars(select(ImportRecord).order_by(ImportRecord.id)))
    grouped: dict[tuple[str, str, str, str], int] = {}
    for record in records:
        key = (
            record.library,
            record.library_version,
            record.library_commit,
            record.license,
        )
        grouped[key] = grouped.get(key, 0) + 1
    return [
        ExternalSourceOut(
            library=library,
            library_version=version,
            library_commit=commit,
            license=license_name,
            imported_statements=count,
            # Mathlib and Lean v4.33.1 have no upstream NOTICE file. Re-check on upgrade.
            notice_status=(
                "absent"
                if library in {"mathlib", "lean"} and version == "v4.33.1"
                else "not_checked"
            ),
        )
        for (library, version, commit, license_name), count in sorted(grouped.items())
    ]
