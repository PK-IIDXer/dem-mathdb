from pathlib import Path
import os
import uuid
import pytest
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from dem.db.base import Base
from dem.db.engine import make_engine
from dem.db.seed import seed_language, seed_inference_rules
from dem.services.symbol import SymbolService
from dem.services.formula import FormulaService
from dem.services.axiom import AxiomService
from dem.services.theorem import TheoremService
from dem.services.proof import ProofService
from dem.services.definition import DefinitionService
from dem.types import (
    AxiomStepInput, DescriptiveFunctionDefinitionInput, FunctionDefinitionInput,
    LogicalDefinitionInput, PredicateDefinitionInput, QuantPropDefinitionInput,
    QuantTermDefinitionInput, SymbolTypeName, TheoremStepInput, Token,
)
from webapi.workspace_export import write_workspace_export, WorkspaceExportMetadata
from scripts.workspace_import import import_workspace

SEED_PHASE = "public_core"


@pytest.fixture
def engines():
    made = []
    def create():
        if os.environ.get('DEM_TEST_DATABASE') == 'postgresql':
            name = 'import_test_' + uuid.uuid4().hex
            admin = make_engine('postgresql+psycopg://dem_dev@localhost:5432/postgres', isolation_level='AUTOCOMMIT')
            with admin.connect() as conn:
                conn.execute(text('CREATE DATABASE ' + name))
            engine = make_engine('postgresql+psycopg://dem_dev@localhost:5432/' + name)
            made.append((engine, admin, name))
        else:
            engine = make_engine('sqlite://')
            made.append((engine, None, None))
        Base.metadata.create_all(engine)
        return engine
    yield create
    for engine, admin, name in reversed(made):
        engine.dispose()
        if admin:
            with admin.connect() as conn:
                conn.execute(text('DROP DATABASE ' + name))
            admin.dispose()


@pytest.fixture
def small_archive(tmp_path, engines):
    engine = engines()
    with Session(engine) as session:
        seed_language(session); seed_inference_rules(session)
        symbols=SymbolService(session)
        x=symbols.register('x',symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value).id,0)
        eq=symbols.get_by_role('equality')
        f=FormulaService(session).register([Token(symbol_id=eq.id),Token(symbol_id=x.id),Token(symbol_id=x.id)])
        DefinitionService(session).register(PredicateDefinitionInput('Reflexive', (x.id,), f.id))
        a=AxiomService(session).register('a',f.id)
        th=TheoremService(session).register('th',f.id)
        ps=ProofService(session); p=ps.create_proof(th.id); ps.add_step(p.id,AxiomStepInput(a.id)); ps.validate(p.id)
        th2=TheoremService(session).register('th2',f.id)
        p2=ps.create_proof(th2.id); ps.add_step(p2.id,TheoremStepInput(p.id)); ps.validate(p2.id)
        session.commit()
        src=tmp_path/'source.dempkg'; write_workspace_export(session,src,WorkspaceExportMetadata('test.roundtrip','test'))
    return src


def test_small_roundtrip(tmp_path, engines, small_archive):
    with Session(engines()) as session:
        result = import_workspace(session, small_archive)
        out = tmp_path / 'out.dempkg'
        write_workspace_export(session, out, result.metadata)
        assert small_archive.read_bytes() == out.read_bytes()


def test_seed_roundtrip(seeded_session, tmp_path, engines):
    src = tmp_path / 'seed.dempkg'
    write_workspace_export(seeded_session, src, WorkspaceExportMetadata('test.seed', 'public-demo'))
    with Session(engines()) as session:
        result = import_workspace(session, src)
        out = tmp_path / 'again.dempkg'
        write_workspace_export(session, out, result.metadata)
        assert src.read_bytes() == out.read_bytes()
        from dataclasses import asdict
        from scripts.import_workspace import peak_rss_bytes
        report = asdict(result)
        report['peak_rss_bytes'] = peak_rss_bytes()
        (tmp_path / 'measurement.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(report)


import json
from zipfile import ZipFile
from webapi.workspace_export import _zip_info, _json_bytes
from scripts.workspace_import import WorkspaceImportError


def tamper(source, destination, change):
    with ZipFile(source) as archive:
        content = {name: archive.read(name) for name in archive.namelist()}
    data = {name: json.loads(value) if name == 'manifest.json' else
            [json.loads(line) for line in value.splitlines()]
            for name, value in content.items() if name != 'NOTICE'}
    change(data)
    with ZipFile(destination, 'w') as archive:
        for name, value in data.items():
            archive.writestr(_zip_info(name), _json_bytes(value) if name == 'manifest.json' else b''.join(map(_json_bytes, value)))
    return destination


def corrupt(data, case):
    proofs = data['proofs.jsonl']
    steps = data['proof_steps.jsonl']
    if case == 'step_formula':
        step = steps[0]
        step['conclusion_formula_public_id'] = next(r['public_id'] for r in data['formulas.jsonl'] if r['public_id'] != step['conclusion_formula_public_id'])
    elif case == 'unproven_status':
        theorem = dict(data['theorems.jsonl'][0], public_id=str(uuid.uuid4()), name='fake', status='proven')
        data['theorems.jsonl'].append(theorem)
    elif case == 'incomplete_verified':
        pid = next(s['proof_public_id'] for s in steps if s['step_kind'] == 'theorem')
        data['proof_steps.jsonl'] = [s for s in steps if s['proof_public_id'] != pid]
    elif case == 'missing_reference':
        data['axioms.jsonl'] = [a for a in data['axioms.jsonl'] if a['origin_kind'] != 'primitive']
    elif case == 'token_hash':
        token = next(v for v in data['formula_tokens.jsonl'] if v['symbol_public_id'])
        token['symbol_public_id'] = next(s['public_id'] for s in data['symbols.jsonl'] if s['public_id'] != token['symbol_public_id'])
    elif case == 'duplicate_public_id':
        data['symbols.jsonl'].append(dict(data['symbols.jsonl'][0]))
    elif case == 'unknown_rule':
        steps[0]['step_kind'] = 'rule'
        steps[0]['inference_rule'] = 'unknown'
    elif case == 'catalog':
        data['inference_rules.jsonl'][0]['premise_count'] = 99
    elif case == 'schema':
        data['manifest.json']['schema_version'] += 1
    elif case == 'unverified_reference':
        pid = next(s['applied_proof_public_id'] for s in steps if s['step_kind'] == 'theorem')
        next(p for p in proofs if p['public_id'] == pid)['status'] = 'draft'
    elif case == 'definition_axiom':
        defining = next(a for a in data['axioms.jsonl'] if a['definition_public_id'])
        defining['formula_public_id'] = next(a['formula_public_id'] for a in data['axioms.jsonl'] if not a['definition_public_id'])
    elif case == 'orphan_detail':
        data['proof_step_args.jsonl'].append(dict(proof_public_id=str(uuid.uuid4()), step_ord=0, arg_ord=0, referenced_step_ord=0))
    elif case == 'hash_only':
        data['formulas.jsonl'][0]['hash'] = '0' * 64
    else:
        raise AssertionError(case)


CASES = ['step_formula', 'unproven_status', 'incomplete_verified', 'missing_reference',
         'token_hash', 'duplicate_public_id', 'unknown_rule', 'catalog', 'schema',
         'unverified_reference', 'definition_axiom', 'orphan_detail', 'hash_only']


@pytest.mark.parametrize('case', CASES)
def test_rejects_tampering_atomically(case, small_archive, tmp_path, engines):
    damaged = tamper(small_archive, tmp_path / 'bad.dempkg', lambda data: corrupt(data, case))
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError):
            import_workspace(session, damaged)
        for table in Base.metadata.sorted_tables:
            assert session.execute(select(table).limit(1)).first() is None, table.name


@pytest.mark.parametrize('guard,case', [('_check_hash', 'hash_only'), ('_check_status', 'unproven_status'), ('_validate_proof', 'incomplete_verified')])
def test_guard_mutations_are_detected(guard, case, small_archive, tmp_path, engines, monkeypatch):
    """Each production rejection assertion fails with its guard removed.

    Validation is disabled ONLY in this deliberately broken mutant; never in
    seed building, performance measurement, or the accepted roundtrip path.
    """
    import scripts.workspace_import as importer
    def change(data):
        corrupt(data, case)
        if guard == '_validate_proof':
            # No derived status is assigned by the mutant, so the forged input
            # also claims conjecture. L2 must still reject its verified proof.
            for theorem in data['theorems.jsonl']:
                theorem['status'] = 'conjecture'
    damaged = tamper(small_archive, tmp_path / 'mutant.dempkg', change)
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError):
            importer.import_workspace(session, damaged)
    monkeypatch.setattr(importer, guard, lambda *args: None)
    with Session(engines()) as session:
        # Assert that the normal rejection test would report DID NOT RAISE.
        with pytest.raises(pytest.fail.Exception, match='DID NOT RAISE'):
            with pytest.raises(WorkspaceImportError):
                importer.import_workspace(session, damaged)


def test_definition_kinds_birth_identity_and_ordinal_gaps(tmp_path, engines):
    from dem.services.definition import DefinitionPublicIdKeys
    with Session(engines()) as session:
        seed_language(session)
        seed_inference_rules(session)
        symbols, formulas = SymbolService(session), FormulaService(session)
        definitions, axioms = DefinitionService(session), AxiomService(session)
        theorems, proofs = TheoremService(session), ProofService(session)
        vt = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value).id
        x, y, z = [symbols.register(name, vt, 0) for name in ('param', 'value', 'witness')]
        term = formulas.register([Token(symbol_id=x.id)])
        definitions.register(FunctionDefinitionInput('identity', (x.id,), term.id))
        eq = symbols.get_by_role('equality')
        body = formulas.register([Token(symbol_id=eq.id), Token(symbol_id=y.id), Token(symbol_id=x.id)])
        statement = formulas.register(definitions.compute_existence_uniqueness_statement_tokens((x.id,), y.id, z.id, body.id))
        axiom = axioms.register('existence', statement.id)
        theorem = theorems.register('existence', statement.id, namespace='local.moved', public_id_key='local.birth::existence')
        early = proofs.create_proof(theorem.id)
        later = proofs.create_proof(theorem.id, import_identity_ordinal=3)
        proofs.add_step(later.id, AxiomStepInput(axiom.id))
        proofs.validate(later.id)
        proofs.add_step(early.id, TheoremStepInput(later.id))
        proofs.validate(early.id)
        discarded = proofs.create_proof(theorem.id)
        session.delete(discarded)
        session.flush()
        definitions.register(DescriptiveFunctionDefinitionInput('chosen', (x.id,), y.id, z.id, body.id, later.id),
            namespace='local.moved', public_id_keys=DefinitionPublicIdKeys('local.birth::chosen', 'local.birth::chosen', 'local.birth::chosen-axiom'))
        from dem.identity import ImportedPublicId
        implication = symbols.get_by_role('implication')
        symbols.register(implication.name, implication.symbol_type_id, implication.arity,
            namespace='local.other', public_id_key=ImportedPublicId('00000000-0000-0000-0000-000000000001'))
        pt = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id
        phi = symbols.register('Phi', pt, 0)
        prop = formulas.register([Token(symbol_id=phi.id)])
        definitions.register(LogicalDefinitionInput('identity_prop', (phi.id,), prop.id))
        psi = symbols.register('Psi', pt, 1)
        forall = symbols.get_by_role('universal_quantifier')
        quantified = formulas.register([Token(symbol_id=forall.id), Token(symbol_id=psi.id), Token(de_bruijn_index=0)])
        definitions.register(QuantPropDefinitionInput('all_like', psi.id, quantified.id))
        constant = symbols.register('constant', symbols.get_symbol_type_by_name(SymbolTypeName.FUNCTION.value).id, 0, is_primitive=True)
        constant_formula = formulas.register([Token(symbol_id=constant.id)])
        definitions.register(QuantTermDefinitionInput('term_binder', psi.id, constant_formula.id))
        session.commit()
        src = tmp_path / 'definitions.dempkg'
        write_workspace_export(session, src, WorkspaceExportMetadata('test.definitions', 'all kinds'))
    with Session(engines()) as session:
        result = import_workspace(session, src)
        out = tmp_path / 'again.dempkg'
        write_workspace_export(session, out, result.metadata)
        assert src.read_bytes() == out.read_bytes()


def test_import_attribution_is_rejected(tmp_path, engines):
    from datetime import datetime, timezone
    from dem.db.models import ImportRecord
    with Session(engines()) as session:
        seed_language(session)
        seed_inference_rules(session)
        symbols = SymbolService(session)
        atom = symbols.register('AttributionProp', symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id, 0)
        formula = FormulaService(session).register([Token(symbol_id=atom.id)])
        theorem = TheoremService(session).register('imported conjecture', formula.id)
        session.add(ImportRecord(theorem_id=theorem.id, source_system='test', source_system_version='1',
            library='example', library_version='1', library_commit='abc', declaration='example.a', module='example',
            file='example.txt', line=1, source_statement='original proposition', source_statement_hash='0'*64,
            universe_params=0, source_axioms='[]', translator_version='1', mapping_table_version='1', prop_encoding='[]',
            check_model='not_run', check_roundtrip='not_run', license='MIT', upstream_origin='unknown',
            retrieved_at=datetime(2026, 10, 17, tzinfo=timezone.utc)))
        session.commit()
        src = tmp_path / 'attribution.dempkg'
        write_workspace_export(session, src, WorkspaceExportMetadata('test.attribution', 'attribution'))
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError, match='External verification records'):
            import_workspace(session, src)
        for table in Base.metadata.sorted_tables:
            assert session.execute(select(table).limit(1)).first() is None, table.name


def test_cli_migrates_empty_database_and_refuses_occupied(tmp_path, small_archive):
    import subprocess
    import sys
    import hashlib
    destination = tmp_path / 'cli.db'
    report_path = tmp_path / 'cli-report.json'
    command = [sys.executable, '-m', 'scripts.import_workspace', str(small_archive),
               '--database-url', 'sqlite:///' + destination.as_posix(),
               '--roundtrip', str(tmp_path / 'cli-again.dempkg'),
               '--report', str(report_path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(report_path.read_text())['byte_identical'] is True
    before = hashlib.sha256(destination.read_bytes()).hexdigest()
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert 'destination is not empty' in json.loads(report_path.read_text())['error']
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == before


@pytest.fixture
def proof_state_archive(tmp_path, engines):
    from dem.errors import ProofValidationError
    def build(kind):
        with Session(engines()) as session:
            seed_language(session)
            seed_inference_rules(session)
            symbols = SymbolService(session)
            prop_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id
            formulas = FormulaService(session)
            p, q = [formulas.register([Token(symbol_id=symbols.register(name, prop_type, 0).id)])
                    for name in ('P', 'Q')]
            axiom = AxiomService(session).register('p', p.id)
            theorem = TheoremService(session).register('goal', p.id if kind in ('complete', 'mixed') else q.id)
            proofs = ProofService(session)
            if kind == 'mixed':
                verified = proofs.create_proof(theorem.id)
                proofs.add_step(verified.id, AxiomStepInput(axiom.id))
                proofs.validate(verified.id)
            draft = proofs.create_proof(theorem.id)
            if kind != 'empty':
                proofs.add_step(draft.id, AxiomStepInput(axiom.id))
            if kind == 'rejected':
                with pytest.raises(ProofValidationError, match='final step'):
                    proofs.validate(draft.id)
                assert draft.status == 'rejected'
            session.commit()
            source = tmp_path / (kind + '.dempkg')
            write_workspace_export(session, source, WorkspaceExportMetadata('test.states', kind))
            return source
    return build


@pytest.mark.parametrize('kind', ['incomplete', 'empty', 'rejected', 'mixed', 'complete'])
def test_proof_states_roundtrip(kind, proof_state_archive, tmp_path, engines):
    source = proof_state_archive(kind)
    with Session(engines()) as session:
        result = import_workspace(session, source)
        output = tmp_path / 'states-again.dempkg'
        write_workspace_export(session, output, result.metadata)
        assert source.read_bytes() == output.read_bytes()


def _claim_rejected(data):
    next(p for p in data['proofs.jsonl'] if p['status'] == 'draft')['status'] = 'rejected'


def test_completed_rejected_proof_is_refused(proof_state_archive, tmp_path, engines):
    source = tamper(proof_state_archive('mixed'), tmp_path / 'false-rejected.dempkg', _claim_rejected)
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError, match='rejected proof passed revalidation'):
            import_workspace(session, source)
        for table in Base.metadata.sorted_tables:
            assert session.execute(select(table).limit(1)).first() is None, table.name


def test_draft_step_tampering_is_refused(proof_state_archive, tmp_path, engines):
    source = tamper(proof_state_archive('incomplete'), tmp_path / 'bad-draft.dempkg',
                    lambda data: corrupt(data, 'step_formula'))
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError, match='conclusion'):
            import_workspace(session, source)
        for table in Base.metadata.sorted_tables:
            assert session.execute(select(table).limit(1)).first() is None, table.name


def test_rejected_failure_guard_mutation(proof_state_archive, tmp_path, engines, monkeypatch):
    import inspect
    import scripts.workspace_import as importer
    source = tamper(proof_state_archive('mixed'), tmp_path / 'mutant-rejected.dempkg', _claim_rejected)
    with Session(engines()) as session:
        with pytest.raises(WorkspaceImportError, match='rejected proof passed revalidation'):
            import_workspace(session, source)
    # Remove only the successful-revalidation rejection, leaving the real
    # validate() call and its rejected-status check intact.
    code = inspect.getsource(importer._validate_rejected_proof)
    guard = "raise WorkspaceImportError('rejected proof passed revalidation')"
    assert guard in code
    namespace = dict(vars(importer))
    exec(code.replace(guard, 'pass'), namespace)
    monkeypatch.setattr(importer, '_validate_rejected_proof', namespace['_validate_rejected_proof'])
    with Session(engines()) as session:
        with pytest.raises(pytest.fail.Exception, match='DID NOT RAISE'):
            with pytest.raises(WorkspaceImportError):
                import_workspace(session, source)
