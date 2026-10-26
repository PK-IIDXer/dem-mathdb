"""Atomic, service-only reconstruction of a workspace archive (always L2).

The caller supplies an empty, migrated database and an idle Session. No HTTP
route imports this module. Archive identities are data, never kernel rules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from dem.db.base import Base
from dem.errors import DemError, ProofValidationError
from dem.db.models.language import SymbolAlias, SymbolRole
from dem.db.seed import seed_language_catalog, seed_inference_rules
from dem.identity import ImportedPublicId, ensure_namespace
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService, DefinitionPublicIdKeys
from dem.services.definition_archive import open_bound_body
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.tag import TagService
from dem.services.theorem import TheoremService
from dem import types as t
from webapi.workspace_export import (
    EXPORT_SCHEMA_VERSION, WORKSPACE_EXPORT_VERSION, WorkspaceExportMetadata,
    _JSONL_EXPORTS, _compile_export_query, _iter_rows, _manifest, _notice,
    _imported_licenses, _json_bytes,
)


class WorkspaceImportError(ValueError):
    """An archive cannot be reconstructed without changing its meaning."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkspaceImportError(message)


def _check_hash(actual, expected):
    require(actual == expected, 'formula hash mismatch')


def _check_status(actual, expected, entity):
    require(actual == expected, f'{entity} status mismatch after L2')


def _validate_rejected_proof(service, proof):
    try:
        service.validate(proof.id)
    except ProofValidationError:
        _check_status(proof.status, 'rejected', 'proof')
    else:
        raise WorkspaceImportError('rejected proof passed revalidation')


def _validate_proof(service, proof, expected):
    if expected == 'draft':
        # A complete but unvalidated draft is still a draft. add_step already
        # checked every step; importing must not promote it to verified.
        _check_status(proof.status, 'draft', 'proof')
    elif expected == 'rejected':
        _validate_rejected_proof(service, proof)
    else:
        require(expected == 'verified', 'unknown proof status')
        service.validate(proof.id)
        _check_status(proof.status, expected, 'proof')


def _projection(table, rows):
    # These fields have dedicated checks against freshly computed values.
    # Keeping one check per invariant also makes guard mutation tests precise.
    omitted = {'status'} if table in ('theorems.jsonl', 'proofs.jsonl') else set()
    if table == 'formulas.jsonl':
        omitted = {'hash'}
    return sorted(_json_bytes({k: v for k, v in r.items() if k not in omitted}) for r in rows)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data):
    return json.loads(data, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          WorkspaceImportError(f"invalid JSON constant: {value}")))


@dataclass(frozen=True)
class WorkspaceImportResult:
    metadata: WorkspaceExportMetadata
    row_counts: dict[str, int]
    l1_seconds: float
    l2_seconds: float
    write_seconds: float


REFERENCE_TABLES = {
    'symbol_public_id': 'symbols', 'new_symbol_public_id': 'symbols',
    'param_symbol_public_id': 'symbols', 'gen_variable_symbol_public_id': 'symbols',
    'source_symbol_public_id': 'symbols', 'formal_param_symbol_public_id': 'symbols',
    'formula_public_id': 'formulas', 'conclusion_formula_public_id': 'formulas',
    'display_formula_public_id': 'formulas', 'target_formula_public_id': 'formulas',
    'body_formula_public_id': 'formulas', 'definition_public_id': 'definitions',
    'axiom_public_id': 'axioms', 'axiom_system_public_id': 'axiom_systems',
    'theorem_public_id': 'theorems', 'proof_public_id': 'proofs',
    'applied_proof_public_id': 'proofs', 'existence_uniqueness_proof_public_id': 'proofs',
}


class _Reconstruction:
    def __init__(self, session, rows, external=None):
        self.session, self.rows = session, rows
        self.external = external or {}
        self.symbols = SymbolService(session)
        self.formulas = FormulaService(session)
        self.definitions = DefinitionService(session)
        self.axioms = AxiomService(session)
        self.theorems = TheoremService(session)
        self.proofs = ProofService(session)
        self.maps = {}
        self.done = defaultdict(dict)
        self.active = set()
        self.l2 = 0.0
        self.allocated_proofs = {}
        for table in ('symbols', 'formulas', 'definitions', 'axioms', 'axiom_systems', 'theorems', 'proofs'):
            values = rows[table + '.jsonl']
            self.maps[table] = {r['public_id']: r for r in values}
            require(len(self.maps[table]) == len(values), f"duplicate public ID in {table}")
            for r in values:
                ImportedPublicId(r['public_id'])
        reference_tables = REFERENCE_TABLES
        self.reference_tables = reference_tables
        for table, values in rows.items():
            require(len(set(map(_json_bytes, values))) == len(values), f'duplicate row in {table}')
            for row in values:
                for field, target in reference_tables.items():
                    if row.get(field) is not None:
                        require(row[field] in self.maps[target] or row[field] in self.external.get(target, {}),
                                f'missing reference: {table}.{field}')
        self.children = {}
        for table, field in (
            ('formula_tokens', 'formula_public_id'), ('definition_formal_params', 'definition_public_id'),
            ('theorem_premises', 'theorem_public_id'), ('proof_steps', 'proof_public_id'),
            ('proof_step_args', 'proof_public_id'), ('proof_step_subst_terms', 'proof_public_id'),
            ('proof_step_subst_props', 'proof_public_id'), ('proof_step_subst_prop_params', 'proof_public_id'),
        ):
            groups = defaultdict(list)
            for r in rows[table + '.jsonl']:
                groups[r[field]].append(r)
            self.children[table] = groups
        self.symbol_def = {r['new_symbol_public_id']: r['public_id'] for r in self.maps['definitions'].values()}
        require(len(self.symbol_def) == len(self.maps['definitions']), 'duplicate defined symbol')
        self.def_axiom = {}
        for r in self.maps['axioms'].values():
            if r['definition_public_id'] is not None:
                require(r['definition_public_id'] not in self.def_axiom, 'multiple defining axioms')
                self.def_axiom[r['definition_public_id']] = r
        self.roles = {r['role']: r['symbol_public_id'] for r in rows['symbol_roles.jsonl']}
        self.token_index = {self.token_key(self.tokens(pid)): pid for pid in self.maps['formulas']}

    @staticmethod
    def token_key(tokens):
        return tuple((r['symbol_public_id'], r['de_bruijn_index']) for r in tokens)

    def ordered(self, table, parent, field='ord'):
        rows = sorted(self.children[table][parent], key=lambda r: r[field])
        require([r[field] for r in rows] == list(range(len(rows))), f'{table}: noncontiguous ordinals')
        return rows

    def tokens(self, pid):
        return self.ordered('formula_tokens', pid, 'position')

    def get(self, table, pid):
        if pid is None:
            return None
        if pid in self.external.get(table, {}):
            return self.external[table][pid]
        if pid in self.done[table]:
            return self.done[table][pid]
        key = (table, pid)
        require(key not in self.active, f'cyclic dependency: {key}')
        require(pid in self.maps[table], f'missing {table}: {pid}')
        self.active.add(key)
        obj = getattr(self, 'make_' + table)(self.maps[table][pid])
        require(obj.public_id == pid, f'{table}: public ID mismatch')
        self.done[table][pid] = obj
        self.active.remove(key)
        return obj

    def fid(self, pid):
        return self.get('formulas', pid).id

    def sid(self, pid):
        return self.get('symbols', pid).id

    def make_symbols(self, r):
        pid = r['public_id']
        if pid in self.symbol_def:
            return self.get('definitions', self.symbol_def[pid]).new_symbol
        fields = {k: r[k] for k in ('name', 'arity', 'is_primitive', 'notation_kind', 'precedence', 'latex_template', 'remarks', 'namespace')}
        obj = self.symbols.register(**fields, symbol_type_id=self.symbols.get_symbol_type_by_name(r['symbol_type']).id,
                                    public_id_key=ImportedPublicId(pid))
        self.discard_automatic_aliases(obj.id)
        self.assign_roles(pid, obj)
        return obj

    def discard_automatic_aliases(self, symbol_id):
        # register() installs convenience spellings in creation order. Package
        # order is by UUID and need not match that history across namespaces.
        # Replay the explicit archive aliases through add_alias after all symbols.
        for alias in self.session.scalars(select(SymbolAlias).where(SymbolAlias.symbol_id == symbol_id)):
            self.session.delete(alias)
        self.session.flush()

    def assign_roles(self, pid, obj):
        for role, target in self.roles.items():
            if target == pid:
                self.symbols.assign_role(role, obj.id)
                row = self.session.get(SymbolRole, role)
                row.remarks = next(r['remarks'] for r in self.rows['symbol_roles.jsonl'] if r['role'] == role)

    def make_formulas(self, r):
        tokens = [t.Token(symbol_id=self.sid(v['symbol_public_id']) if v['symbol_public_id'] else None,
                          de_bruijn_index=v['de_bruijn_index']) for v in self.tokens(r['public_id'])]
        obj = self.formulas.register(tokens, remarks=r['remarks'])
        _check_hash(obj.hash, r['hash'])
        require(obj.public_id == r['public_id'], 'formula public ID mismatch')
        require(obj.token_count == r['token_count'] and obj.formula_type.name == r['formula_type'], 'formula shape mismatch')
        obj.description, obj.remarks = r['description'], r['remarks']
        return obj

    def symbol_record(self, pid):
        if pid in self.maps['symbols']:
            return self.maps['symbols'][pid]
        symbol = self.external['symbols'][pid]
        return {'symbol_type': symbol.symbol_type.name, 'arity': symbol.arity}

    def _open_body(self, tokens, params):
        return open_bound_body(tokens, params, self.symbol_record, self.rows['symbol_types.jsonl'], require)

    def make_definitions(self, r):
        sr = self.maps['symbols'][r['new_symbol_public_id']]
        ar = self.def_axiom[r['public_id']]
        params = [p['param_symbol_public_id'] for p in self.ordered('definition_formal_params', r['public_id'])]
        tokens = self.tokens(ar['formula_public_id'])
        kind = r['kind']
        require(len(tokens) >= 2, 'invalid defining axiom')
        # Role symbols are registered before DefinitionService computes its axiom.
        for role in ('biconditional', 'equality', 'universal_quantifier'):
            if role in self.roles:
                self.sid(self.roles[role])
        if kind in ('predicate', 'function'):
            body = self._open_body(tokens[len(params) + 2 + len(params):], params)
        elif kind == 'logical':
            body = tokens[2 + len(params):]
        elif kind in ('quant_prop', 'quant_term'):
            body = tokens[4:]
        elif kind == 'function_desc':
            # The value variable's spelling was erased by abstraction. Recover a
            # body already present in the archive; never invent a new formula.
            free_body_symbols = {v['symbol_public_id'] for v in tokens[2 * len(params) + 5:]}
            candidates = [p for p in sorted((*self.maps['symbols'], *self.external.get('symbols', {})))
                          if self.symbol_record(p)['symbol_type'] == t.SymbolTypeName.FREE_TERM_VAR.value
                          and p not in params and p not in free_body_symbols]
            body = None
            for value in candidates:
                trial = self._open_body(tokens[2 * len(params) + 5:], params + [value])
                if self.token_key(trial) in self.token_index:
                    body = trial
                    break
            require(body is not None, 'cannot reconstruct descriptive definition body')
        else:
            raise WorkspaceImportError(f'unknown definition kind: {kind}')
        body_pid = self.token_index.get(self.token_key(body))
        require(body_pid is not None, 'definition body missing from archive')
        kwargs = dict(name=r['name'], body_formula_id=self.fid(body_pid), remarks=r['remarks'], latex_template=sr['latex_template'])
        pids = tuple(self.sid(p) for p in params)
        classes = {'predicate': t.PredicateDefinitionInput, 'function': t.FunctionDefinitionInput,
                   'logical': t.LogicalDefinitionInput, 'quant_prop': t.QuantPropDefinitionInput,
                   'quant_term': t.QuantTermDefinitionInput, 'function_desc': t.DescriptiveFunctionDefinitionInput}
        if kind in ('quant_prop', 'quant_term'):
            require(len(pids) == 1, 'quantifier definition parameter count')
            kwargs['param_symbol_id'] = pids[0]
        else:
            kwargs['param_symbol_ids'] = pids
        if kind == 'predicate':
            kwargs.update(requires_existence_proof=r['requires_existence_proof'], requires_uniqueness_proof=r['requires_uniqueness_proof'])
        if kind == 'function_desc':
            free = {v['symbol_public_id'] for v in body}
            witness = next((p for p in candidates if p != value and p not in free), None)
            require(witness is not None, 'descriptive definition needs a fresh witness')
            kwargs.update(value_symbol_id=self.sid(value), uniqueness_witness_symbol_id=self.sid(witness),
                          existence_uniqueness_proof_id=self.get('proofs', r['existence_uniqueness_proof_public_id']).id)
        obj = self.definitions.register(classes[kind](**kwargs), namespace=sr['namespace'],
                public_id_keys=DefinitionPublicIdKeys(ImportedPublicId(sr['public_id']), ImportedPublicId(r['public_id']), ImportedPublicId(ar['public_id'])))
        symbol = obj.new_symbol
        self.discard_automatic_aliases(symbol.id)
        self.done['symbols'][sr['public_id']] = symbol
        self.symbols.set_notation(symbol.id, sr['notation_kind'], sr['precedence'])
        symbol.remarks = sr['remarks']
        self.assign_roles(sr['public_id'], symbol)
        axiom = self.definitions.get_axiom(obj.id)
        require(axiom.formula.public_id == ar['formula_public_id'], 'reconstructed defining axiom mismatch')
        # Names and display metadata do not participate in conservativity.
        axiom.name, axiom.description, axiom.remarks = ar['name'], ar['description'], ar['remarks']
        axiom.namespace_id = ensure_namespace(self.session, ar['namespace']).id
        self.done['axioms'][ar['public_id']] = axiom
        obj.description = r['description']
        return obj

    def make_axioms(self, r):
        if r['definition_public_id']:
            self.get('definitions', r['definition_public_id'])
            return self.done['axioms'][r['public_id']]
        require(r['origin_kind'] == 'primitive', 'invalid axiom origin')
        return self.axioms.register(name=r['name'], formula_id=self.fid(r['formula_public_id']),
            namespace=r['namespace'], description=r['description'], remarks=r['remarks'], public_id_key=ImportedPublicId(r['public_id']))

    def make_axiom_systems(self, r):
        obj = self.axioms.register_system(r['name'], remarks=r['remarks'], namespace=r['namespace'], public_id_key=ImportedPublicId(r['public_id']))
        obj.comparison_rank = r['comparison_rank']
        return obj

    def make_theorems(self, r):
        return self.theorems.register(name=r['name'], conclusion_formula_id=self.fid(r['conclusion_formula_public_id']),
            premise_formula_ids=[self.fid(p['formula_public_id']) for p in self.ordered('theorem_premises', r['public_id'])],
            namespace=r['namespace'], description=r['description'], remarks=r['remarks'], public_id_key=ImportedPublicId(r['public_id']))

    def make_proofs(self, r):
        pid = r['public_id']
        theorem = self.get('theorems', r['theorem_public_id'])
        # Allocate identities independently of validation order. An earlier
        # surviving proof may cite a later proof of the same theorem.
        for other in sorted(self.maps['proofs'].values(), key=lambda v: v['identity_ordinal']):
            if other['theorem_public_id'] == r['theorem_public_id'] and other['public_id'] not in self.allocated_proofs:
                self.allocated_proofs[other['public_id']] = self.proofs.create_proof(
                    theorem.id, name=other['name'], remarks=other['remarks'],
                    import_identity_ordinal=other['identity_ordinal'])
        steps = self.ordered('proof_steps', pid)
        for step in steps:
            if step['applied_proof_public_id']:
                self.get('proofs', step['applied_proof_public_id'])
        obj = self.allocated_proofs[pid]
        for step in steps:
            n = step['ord']
            args = sorted([v for v in self.children['proof_step_args'][pid] if v['step_ord'] == n], key=lambda v: v['arg_ord'])
            require([v['arg_ord'] for v in args] == list(range(len(args))), 'invalid step argument ordinals')
            args = tuple(v['referenced_step_ord'] for v in args)
            terms = tuple(t.TermSubst(self.sid(v['source_symbol_public_id']), self.fid(v['target_formula_public_id']))
                          for v in self.children['proof_step_subst_terms'][pid] if v['step_ord'] == n)
            props = []
            for v in self.children['proof_step_subst_props'][pid]:
                if v['step_ord'] != n:
                    continue
                params = sorted([p for p in self.children['proof_step_subst_prop_params'][pid]
                    if p['step_ord'] == n and p['source_symbol_public_id'] == v['source_symbol_public_id']], key=lambda p: p['ord'])
                require([p['ord'] for p in params] == list(range(len(params))), 'invalid substitution parameter ordinals')
                props.append(t.PropSubst(self.sid(v['source_symbol_public_id']), self.fid(v['body_formula_public_id']),
                                        tuple(self.sid(p['formal_param_symbol_public_id']) for p in params)))
            subst = t.Substitution(tuple(props), terms)
            kind = step['step_kind']
            if kind == 'premise':
                inp = t.PremiseStepInput(step['premise_ord'])
            elif kind == 'assumption':
                inp = t.AssumptionStepInput()
            elif kind == 'axiom':
                inp = t.AxiomStepInput(self.get('axioms', step['axiom_public_id']).id, subst)
            elif kind == 'theorem':
                inp = t.TheoremStepInput(self.get('proofs', step['applied_proof_public_id']).id, subst, args)
            elif kind == 'rule':
                rule = self.proofs.get_inference_rule_by_name(step['inference_rule'])
                if rule.kind == 'modus_ponens':
                    inp = t.MPStepInput(*args)
                elif rule.kind == 'generalization':
                    inp = t.GenStepInput(*args, self.sid(step['gen_variable_symbol_public_id']))
                elif rule.kind == 'implication_intro':
                    inp = t.ImplicationIntroStepInput(*args)
                else:
                    raise WorkspaceImportError('unsupported runtime inference rule')
            else:
                raise WorkspaceImportError(f'unknown step kind: {kind}')
            row = self.proofs.add_step(obj.id, inp, conclusion_formula_id=self.fid(step['conclusion_formula_public_id']))
            require(row.conclusion_formula.public_id == step['conclusion_formula_public_id'], 'step conclusion mismatch')
            row.remarks = step['remarks']
        start = perf_counter()
        _validate_proof(self.proofs, obj, r['status'])
        self.l2 += perf_counter() - start
        return obj


def validate_rows(session, rows):
    """Check exported field schemas without inserting runtime or content rows."""
    for item in _JSONL_EXPORTS:
        columns = set(session.execute(text(_compile_export_query(item.query, session.get_bind().dialect))).keys())
        for row in rows[item.filename]:
            require(type(row) is dict and set(row) == columns, f'invalid fields: {item.filename}')
            for key in item.boolean_fields:
                require(type(row[key]) is bool, f'invalid boolean: {item.filename}.{key}')
            for key, value in row.items():
                if key in ('ord', 'position', 'step_ord', 'arg_ord', 'referenced_step_ord', 'identity_ordinal', 'next_ordinal', 'arity', 'token_count', 'de_bruijn_index', 'premise_ord') and value is not None:
                    require(type(value) is int and value >= 0, f'invalid integer: {key}')


def reconstruct_rows(session, rows, build):
    """Replay the common L2 service path; callers own transaction and read-back."""
    for r in rows['namespaces.jsonl']:
        ensure_namespace(session, r['name'])
    for table in ('symbols', 'formulas', 'definitions', 'axioms', 'axiom_systems', 'theorems', 'proofs'):
        for pid in build.maps[table]:
            build.get(table, pid)
    for r in rows['proof_identity_sequences.jsonl']:
        build.proofs.reserve_import_identity_sequence(
            build.get('theorems', r['theorem_public_id']).id, r['next_ordinal'])
    for pid, obj in build.done['definitions'].items():
        display = build.maps['definitions'][pid]['display_formula_public_id']
        build.definitions.set_display_formula(obj.id, build.fid(display) if display else None)
    for r in rows['axiom_system_members.jsonl']:
        build.axioms.add_to_system(build.get('axiom_systems', r['axiom_system_public_id']).id, build.get('axioms', r['axiom_public_id']).id)
    for r in rows['symbol_aliases.jsonl']:
        existing = session.scalar(select(SymbolAlias).where(SymbolAlias.alias == r['alias']))
        if existing is None:
            build.symbols.add_alias(build.sid(r['symbol_public_id']), r['alias'], r['source'])
        else:
            require(existing.symbol_id == build.sid(r['symbol_public_id']), 'alias target mismatch')
            existing.source = r['source']
    tags = TagService(session)
    tag_ids = {r['name']: tags.get_or_create(r['name']).id for r in rows['tags.jsonl']}
    for r in rows['theorem_tags.jsonl']:
        tags.attach('theorem', build.get('theorems', r['theorem_public_id']).id, tag_ids[r['tag_name']])
    session.flush()
    for pid, obj in build.done['theorems'].items():
        _check_status(obj.status, build.maps['theorems'][pid]['status'], 'theorem')


def _import_workspace(session: Session, source: Path) -> WorkspaceImportResult:
    """Commit one complete import, or roll back every content row on failure.

    Requires an idle session and empty migrated tables (including runtime rows).
    L2 time measures validate(); write time includes add_step's mandatory checks.
    """
    require(not session.in_transaction(), 'import requires an idle session')
    start = perf_counter()
    with ZipFile(source) as archive:
        names = archive.namelist()
        expected = {'manifest.json', *(i.filename for i in _JSONL_EXPORTS)}
        require(len(names) == len(set(names)), 'duplicate archive member')
        require(set(names) in (expected, expected | {'NOTICE'}), 'unexpected/missing archive members')
        manifest = _json(archive.read('manifest.json'))
        require(type(manifest['schema_version']) is int and manifest['schema_version'] == EXPORT_SCHEMA_VERSION, 'unsupported schema_version')
        require(manifest['version'] == WORKSPACE_EXPORT_VERSION and manifest['depends'] == {}, 'unsupported package version/dependencies')
        metadata = WorkspaceExportMetadata(manifest['package'], manifest['description'])
        rows = {i.filename: [_json(line) for line in archive.read(i.filename).splitlines()] for i in _JSONL_EXPORTS}
        notice = archive.read('NOTICE').decode('utf-8') if 'NOTICE' in names else None
    require(not rows['import_records.jsonl'],
            'External verification records are not accepted until their checks can be rerun')
    l1 = perf_counter() - start
    with session.begin():
        for table in Base.metadata.sorted_tables:
            require(session.execute(select(table).limit(1)).first() is None, f'destination is not empty: {table.name}')
        seed_language_catalog(session)
        seed_inference_rules(session)
        validate_rows(session, rows)
        for item in _JSONL_EXPORTS:
            if item.filename in ('formula_types.jsonl', 'symbol_types.jsonl', 'inference_rules.jsonl'):
                runtime = list(_iter_rows(session, item, frozenset()))
                require(runtime == rows[item.filename], f'runtime catalog mismatch: {item.filename}')
        build = _Reconstruction(session, rows)
        l1 = perf_counter() - start
        writing = perf_counter()
        reconstruct_rows(session, rows, build)
        write_seconds = perf_counter() - writing - build.l2
        checking = perf_counter()
        # Exhaustive read-back catches orphan detail rows, extra fields on step
        # kinds, duplicate relations, derived flags, namespace and metadata loss.
        for item in _JSONL_EXPORTS:
            actual = list(_iter_rows(session, item, frozenset()))
            require(_projection(item.filename, actual) == _projection(item.filename, rows[item.filename]),
                    f'reconstructed content mismatch: {item.filename}')
        require(manifest == _manifest(metadata, _imported_licenses(session)), 'manifest/runtime metadata mismatch')
        require(notice == _notice(session), 'NOTICE mismatch')
        l1 += perf_counter() - checking
        committing = perf_counter()
    write_seconds += perf_counter() - committing
    return WorkspaceImportResult(metadata, {k: len(v) for k, v in rows.items()}, l1, build.l2, write_seconds)


def import_workspace(session: Session, source: Path) -> WorkspaceImportResult:
    """Atomically import an archive; discard failed service caches before reuse."""
    try:
        return _import_workspace(session, source)
    except (DemError, IntegrityError, KeyError, TypeError, ValueError) as exc:
        # Service caches can contain rows whose transaction has rolled back.
        # The session belongs exclusively to this importer (idle on entry).
        if not session.in_transaction():
            session.info.clear()
        if isinstance(exc, WorkspaceImportError):
            raise
        raise WorkspaceImportError(f'{type(exc).__name__}: {exc}') from exc
