from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from sqlalchemy import text
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Session

from dem import __version__ as dem_version
from dem.db.ordering import compile_utf8_sort_key


EXPORT_SCHEMA_VERSION = 1
WORKSPACE_EXPORT_VERSION = "0.0.0"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_UTF8_SORT_TOKEN = re.compile(r"\[\[utf8:([A-Za-z_][A-Za-z0-9_.]*)\]\]")


@dataclass(frozen=True)
class WorkspaceExportMetadata:
    package: str
    description: str


@dataclass(frozen=True)
class WorkspaceExportResult:
    path: Path
    row_counts: dict[str, int]


@dataclass(frozen=True)
class _JsonlExport:
    filename: str
    query: str
    boolean_fields: frozenset[str] = frozenset()


# References use transportable public IDs, formula hashes, or stable runtime names;
# database-local integer IDs are deliberately absent from every projection.
_JSONL_EXPORTS = (
    _JsonlExport(
        "namespaces.jsonl",
        """
        SELECT child.name AS name, parent.name AS parent
        FROM namespace AS child
        LEFT JOIN namespace AS parent ON parent.id = child.parent_id
        ORDER BY [[utf8:child.name]]
        """,
    ),
    _JsonlExport(
        "formula_types.jsonl",
        """
        SELECT name, remarks
        FROM formula_type
        ORDER BY [[utf8:name]]
        """,
    ),
    _JsonlExport(
        "symbol_types.jsonl",
        """
        SELECT st.name AS name,
               output_type.name AS output_formula_type,
               input_type.name AS input_formula_type,
               st.fixed_arity AS fixed_arity,
               st.is_quantifier AS is_quantifier,
               st.remarks AS remarks
        FROM symbol_type AS st
        JOIN formula_type AS output_type ON output_type.id = st.output_formula_type_id
        LEFT JOIN formula_type AS input_type ON input_type.id = st.input_formula_type_id
        ORDER BY [[utf8:st.name]]
        """,
        frozenset({"is_quantifier"}),
    ),
    _JsonlExport(
        "symbols.jsonl",
        """
        SELECT s.public_id AS public_id,
               s.name AS name,
               st.name AS symbol_type,
               s.arity AS arity,
               s.is_primitive AS is_primitive,
               n.name AS namespace,
               s.notation_kind AS notation_kind,
               s.precedence AS precedence,
               s.latex_template AS latex_template,
               s.remarks AS remarks
        FROM symbol AS s
        JOIN symbol_type AS st ON st.id = s.symbol_type_id
        JOIN namespace AS n ON n.id = s.namespace_id
        ORDER BY [[utf8:s.public_id]]
        """,
        frozenset({"is_primitive"}),
    ),
    _JsonlExport(
        "symbol_aliases.jsonl",
        """
        SELECT s.public_id AS symbol_public_id, sa.alias AS alias, sa.source AS source
        FROM symbol_alias AS sa
        JOIN symbol AS s ON s.id = sa.symbol_id
        ORDER BY [[utf8:s.public_id]], [[utf8:sa.alias]]
        """,
    ),
    _JsonlExport(
        "symbol_roles.jsonl",
        """
        SELECT sr.role AS role, s.public_id AS symbol_public_id, sr.remarks AS remarks
        FROM symbol_role AS sr
        JOIN symbol AS s ON s.id = sr.symbol_id
        ORDER BY [[utf8:sr.role]]
        """,
    ),
    _JsonlExport(
        "inference_rules.jsonl",
        """
        SELECT name, kind, tier, elimination_procedure, premise_count,
               requires_variable_param, remarks
        FROM inference_rule
        ORDER BY [[utf8:name]]
        """,
        frozenset({"requires_variable_param"}),
    ),
    _JsonlExport(
        "formulas.jsonl",
        """
        SELECT f.public_id AS public_id,
               ft.name AS formula_type,
               f.hash AS hash,
               f.token_count AS token_count,
               f.description AS description,
               f.remarks AS remarks
        FROM formula AS f
        JOIN formula_type AS ft ON ft.id = f.formula_type_id
        ORDER BY [[utf8:f.hash]]
        """,
    ),
    _JsonlExport(
        "formula_tokens.jsonl",
        """
        SELECT f.public_id AS formula_public_id,
               token.position AS position,
               s.public_id AS symbol_public_id,
               token.de_bruijn_index AS de_bruijn_index
        FROM formula AS f
        JOIN formula_token AS token ON token.formula_id = f.id
        LEFT JOIN symbol AS s ON s.id = token.symbol_id
        ORDER BY [[utf8:f.hash]], token.position
        """,
    ),
    _JsonlExport(
        "definitions.jsonl",
        """
        SELECT d.public_id AS public_id,
               d.name AS name,
               d.kind AS kind,
               symbol.public_id AS new_symbol_public_id,
               d.requires_existence_proof AS requires_existence_proof,
               d.requires_uniqueness_proof AS requires_uniqueness_proof,
               proof.public_id AS existence_uniqueness_proof_public_id,
               formula.public_id AS display_formula_public_id,
               d.description AS description,
               d.remarks AS remarks
        FROM definition AS d
        JOIN symbol ON symbol.id = d.new_symbol_id
        LEFT JOIN proof ON proof.id = d.existence_uniqueness_proof_id
        LEFT JOIN formula ON formula.id = d.display_formula_id
        ORDER BY [[utf8:d.public_id]]
        """,
        frozenset({"requires_existence_proof", "requires_uniqueness_proof"}),
    ),
    _JsonlExport(
        "definition_formal_params.jsonl",
        """
        SELECT d.public_id AS definition_public_id,
               param.ord AS ord,
               symbol.public_id AS param_symbol_public_id
        FROM definition_formal_param AS param
        JOIN definition AS d ON d.id = param.definition_id
        JOIN symbol ON symbol.id = param.param_symbol_id
        ORDER BY [[utf8:d.public_id]], param.ord
        """,
    ),
    _JsonlExport(
        "axioms.jsonl",
        """
        SELECT a.public_id AS public_id,
               a.name AS name,
               namespace.name AS namespace,
               formula.public_id AS formula_public_id,
               a.origin_kind AS origin_kind,
               definition.public_id AS definition_public_id,
               a.description AS description,
               a.remarks AS remarks
        FROM axiom AS a
        JOIN namespace ON namespace.id = a.namespace_id
        JOIN formula ON formula.id = a.formula_id
        LEFT JOIN definition ON definition.id = a.definition_id
        ORDER BY [[utf8:a.public_id]]
        """,
    ),
    _JsonlExport(
        "axiom_systems.jsonl",
        """
        SELECT name, remarks
        FROM axiom_system
        ORDER BY [[utf8:name]]
        """,
    ),
    _JsonlExport(
        "axiom_system_members.jsonl",
        """
        SELECT system.name AS axiom_system,
               axiom.public_id AS axiom_public_id
        FROM axiom_system_member AS member
        JOIN axiom_system AS system ON system.id = member.axiom_system_id
        JOIN axiom ON axiom.id = member.axiom_id
        ORDER BY [[utf8:system.name]], [[utf8:axiom.public_id]]
        """,
    ),
    _JsonlExport(
        "theorems.jsonl",
        """
        SELECT theorem.public_id AS public_id,
               namespace.name AS namespace,
               theorem.name AS name,
               formula.public_id AS conclusion_formula_public_id,
               theorem.status AS status,
               theorem.description AS description,
               theorem.remarks AS remarks
        FROM theorem
        JOIN namespace ON namespace.id = theorem.namespace_id
        JOIN formula ON formula.id = theorem.conclusion_formula_id
        ORDER BY [[utf8:theorem.public_id]]
        """,
    ),
    _JsonlExport(
        "theorem_premises.jsonl",
        """
        SELECT theorem.public_id AS theorem_public_id,
               premise.ord AS ord,
               formula.public_id AS formula_public_id
        FROM theorem_premise AS premise
        JOIN theorem ON theorem.id = premise.theorem_id
        JOIN formula ON formula.id = premise.formula_id
        ORDER BY [[utf8:theorem.public_id]], premise.ord
        """,
    ),
    _JsonlExport(
        "tags.jsonl",
        """
        SELECT name FROM tag
        ORDER BY [[utf8:name]]
        """,
    ),
    _JsonlExport(
        "theorem_tags.jsonl",
        """
        SELECT theorem.public_id AS theorem_public_id, tag.name AS tag_name
        FROM theorem_tag
        JOIN theorem ON theorem.id = theorem_tag.theorem_id
        JOIN tag ON tag.id = theorem_tag.tag_id
        ORDER BY [[utf8:theorem.public_id]], [[utf8:tag.name]]
        """,
    ),
    _JsonlExport(
        "proofs.jsonl",
        """
        SELECT proof.public_id AS public_id,
               theorem.public_id AS theorem_public_id,
               proof.identity_ordinal AS identity_ordinal,
               proof.name AS name,
               proof.status AS status,
               proof.remarks AS remarks
        FROM proof
        JOIN theorem ON theorem.id = proof.theorem_id
        ORDER BY [[utf8:proof.public_id]]
        """,
    ),
    _JsonlExport(
        "proof_steps.jsonl",
        """
        SELECT proof.public_id AS proof_public_id,
               step.ord AS ord,
               step.step_kind AS step_kind,
               formula.public_id AS conclusion_formula_public_id,
               step.premise_ord AS premise_ord,
               axiom.public_id AS axiom_public_id,
               applied_proof.public_id AS applied_proof_public_id,
               inference_rule.name AS inference_rule,
               gen_symbol.public_id AS gen_variable_symbol_public_id,
               step.remarks AS remarks
        FROM proof_step AS step
        JOIN proof ON proof.id = step.proof_id
        JOIN formula ON formula.id = step.conclusion_formula_id
        LEFT JOIN axiom ON axiom.id = step.axiom_id
        LEFT JOIN proof AS applied_proof ON applied_proof.id = step.applied_proof_id
        LEFT JOIN inference_rule ON inference_rule.id = step.inference_rule_id
        LEFT JOIN symbol AS gen_symbol ON gen_symbol.id = step.gen_variable_symbol_id
        ORDER BY [[utf8:proof.public_id]], step.ord
        """,
    ),
    _JsonlExport(
        "proof_step_args.jsonl",
        """
        SELECT proof.public_id AS proof_public_id,
               arg.step_ord AS step_ord,
               arg.arg_ord AS arg_ord,
               arg.referenced_step_ord AS referenced_step_ord
        FROM proof_step_arg AS arg
        JOIN proof ON proof.id = arg.proof_id
        ORDER BY [[utf8:proof.public_id]], arg.step_ord, arg.arg_ord
        """,
    ),
    _JsonlExport(
        "proof_step_subst_terms.jsonl",
        """
        SELECT proof.public_id AS proof_public_id,
               subst.step_ord AS step_ord,
               source.public_id AS source_symbol_public_id,
               target.public_id AS target_formula_public_id
        FROM proof_step_subst_term AS subst
        JOIN proof ON proof.id = subst.proof_id
        JOIN symbol AS source ON source.id = subst.source_symbol_id
        JOIN formula AS target ON target.id = subst.target_formula_id
        ORDER BY [[utf8:proof.public_id]], subst.step_ord, [[utf8:source.public_id]]
        """,
    ),
    _JsonlExport(
        "proof_step_subst_props.jsonl",
        """
        SELECT proof.public_id AS proof_public_id,
               subst.step_ord AS step_ord,
               source.public_id AS source_symbol_public_id,
               body.public_id AS body_formula_public_id
        FROM proof_step_subst_prop AS subst
        JOIN proof ON proof.id = subst.proof_id
        JOIN symbol AS source ON source.id = subst.source_symbol_id
        JOIN formula AS body ON body.id = subst.body_formula_id
        ORDER BY [[utf8:proof.public_id]], subst.step_ord, [[utf8:source.public_id]]
        """,
    ),
    _JsonlExport(
        "proof_step_subst_prop_params.jsonl",
        """
        SELECT proof.public_id AS proof_public_id,
               param.step_ord AS step_ord,
               source.public_id AS source_symbol_public_id,
               param.ord AS ord,
               formal.public_id AS formal_param_symbol_public_id
        FROM proof_step_subst_prop_param AS param
        JOIN proof ON proof.id = param.proof_id
        JOIN symbol AS source ON source.id = param.source_symbol_id
        JOIN symbol AS formal ON formal.id = param.formal_param_symbol_id
        ORDER BY [[utf8:proof.public_id]], param.step_ord, [[utf8:source.public_id]], param.ord
        """,
    ),
)


def export_member_names() -> tuple[str, ...]:
    return tuple(item.filename for item in _JSONL_EXPORTS)


def _zip_info(filename: str) -> ZipInfo:
    info = ZipInfo(filename, _ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    return info


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _manifest(metadata: WorkspaceExportMetadata) -> dict[str, object]:
    major, minor, *_ = (int(part) for part in dem_version.split("."))
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "package": metadata.package,
        "version": WORKSPACE_EXPORT_VERSION,
        "dem_runtime": f">={dem_version},<{major}.{minor + 1}.0",
        "depends": {},
        "license": None,
        "description": metadata.description,
        "empty_field_reasons": {
            "depends": "Package dependency tracking starts in Phase 5-6.",
            "license": "The workspace model does not yet store license metadata.",
        },
        "identity": {
            "entities": "public_id",
            "formulas": "public_id and hash",
            "non_formula_identity": "public_id only; canonical hashes start in Phase 5-6",
        },
        "derived_fields": {
            "theorems.jsonl": ["status"],
            "proofs.jsonl": ["status"],
        },
    }


def _iter_rows(
    session: Session, item: _JsonlExport
) -> Iterable[dict[str, object]]:
    query = _compile_export_query(item.query, session.get_bind().dialect)
    result = session.execute(
        text(query).execution_options(stream_results=True, yield_per=2_000)
    )
    for row in result.mappings():
        record = dict(row)
        for field in item.boolean_fields:
            record[field] = bool(record[field])
        yield record


def _compile_export_query(query: str, dialect: Dialect) -> str:
    query = _UTF8_SORT_TOKEN.sub(
        lambda match: compile_utf8_sort_key(match.group(1), dialect),
        query,
    )
    if _UTF8_SORT_TOKEN.search(query):
        raise ValueError("unresolved UTF-8 ordering token")
    return query


def write_workspace_export(
    session: Session,
    destination: Path,
    metadata: WorkspaceExportMetadata,
) -> WorkspaceExportResult:
    """Write one portable, deterministic, disk-streamed workspace archive."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    row_counts: dict[str, int] = {}
    with ZipFile(
        destination,
        mode="w",
        compression=ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        archive.writestr(_zip_info("manifest.json"), _json_bytes(_manifest(metadata)))
        for item in _JSONL_EXPORTS:
            count = 0
            with archive.open(_zip_info(item.filename), mode="w", force_zip64=True) as member:
                for record in _iter_rows(session, item):
                    member.write(_json_bytes(record))
                    count += 1
            row_counts[item.filename] = count
    return WorkspaceExportResult(path=destination, row_counts=row_counts)


def create_workspace_export(
    session: Session, metadata: WorkspaceExportMetadata
) -> WorkspaceExportResult:
    descriptor, filename = tempfile.mkstemp(prefix="dem-workspace-", suffix=".dempkg")
    os.close(descriptor)
    path = Path(filename)
    try:
        return write_workspace_export(session, path, metadata)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
