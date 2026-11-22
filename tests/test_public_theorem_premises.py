"""Regression coverage for migrating public theorem antecedents to premises."""

import asyncio
from dataclasses import asdict
import hashlib
from inspect import getsource
from itertools import permutations
import json
from pathlib import Path
from textwrap import dedent
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from beta_http import asgi_request
from dem.api import DemServices
from dem.db.models import Axiom, AxiomSystem, Formula, Proof, Symbol, Theorem
from dem.db.seeds import public_set_tools
from dem.db.seeds.public_mk import STATEMENTS as MK_EXISTENCE
from dem.db.seeds.public_relations_data import CLASS_VALUES, COMPOSITION_STATEMENTS, PREIMAGE_STATEMENTS
from dem.db.seeds.public_relations_data import RELATION_VALUES
from dem.errors import ProofValidationError, ValidationError
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.types import PremiseStepInput
from webapi.deps import dem_services
from webapi.routers.theorems import router


SEED_PHASE = 'public_class_relations'
BASELINE = json.loads((Path(__file__).parent / 'fixtures/public-theorem-premises-baseline.json').read_bytes())
MIGRATION = BASELINE['migration']


def snapshot(session):
    """Record each statement and proof using public identities and formula hashes."""
    fs, ps, ts = FormulaService(session), ProofService(session), TheoremService(session)
    systems = list(session.scalars(select(AxiomSystem).order_by(AxiomSystem.id)))
    hashes = dict(session.execute(select(Formula.id, Formula.hash)).all())
    symbols = dict(session.execute(select(Symbol.id, Symbol.public_id)).all())
    axioms = dict(session.execute(select(Axiom.id, Axiom.public_id)).all())
    proofs = {p.id: p for p in session.scalars(select(Proof))}
    theorems = {t.id: t for t in session.scalars(select(Theorem))}
    sources = {
        'axiom_id': axioms,
        'applied_proof_id': {key: p.public_id for key, p in proofs.items()},
        'gen_variable_symbol_id': symbols,
        'source_symbol_id': symbols,
        'target_formula_id': hashes,
        'body_formula_id': hashes,
    }

    def normalize(value, key=''):
        if key in sources:
            return sources[key][value]
        if key == 'formal_param_symbol_ids':
            return [symbols[i] for i in value]
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        return value

    result = {}
    for t in theorems.values():
        proof_rows = {}
        for p in ps.list_for_theorem(t.id):
            assert p.status == 'verified', t.name
            steps = ps.list_steps(p.id)
            assert steps
            data = [
                (type(spec).__name__, normalize(asdict(spec)), hashes[step.conclusion_formula_id])
                for (spec, _), step in zip(ps.reconstruct_steps(p.id), steps, strict=True)
            ]
            proof_rows[p.public_id] = {
                'steps': len(steps),
                'step_hash': hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'direct_axioms': sorted({axioms[step.axiom_id] for step in steps if step.axiom_id is not None}),
                'cites': sorted({theorems[proofs[step.applied_proof_id].theorem_id].name
                                 for step in steps if step.applied_proof_id is not None}),
                'axioms': sorted(a.name for a in ps.list_used_axioms(p.id)),
                'valid': [system.name for system in systems if ps.is_valid_in_system(p.id, system.id)],
            }
        premises = ts.list_premises(t.id)
        result[t.name] = {
            'id': t.public_id,
            'hash': hashes[t.conclusion_formula_id],
            'dss': fs.print_text(ps._tokens_for_formula(t.conclusion_formula_id)),
            'premises': [{'hash': f.hash, 'dss': fs.print_text(ps._tokens_for_formula(f.id))} for _, f in premises],
            'proofs': proof_rows,
        }
    return result

def assert_migration(before, after):
    assert before.keys() == after.keys()
    assert len(MIGRATION) == 42
    affected = {
        name for name, row in before.items() if name not in MIGRATION
        and any(set(p['cites']) & MIGRATION.keys() for p in row['proofs'].values())
    }
    assert affected == {name for name, _, _ in MK_EXISTENCE}
    assert len(before.keys() - MIGRATION.keys() - affected) == 40
    for name, old in before.items():
        new = after[name]
        assert new['id'] == old['id'], name
        if name in MIGRATION:
            assert not old['premises'], name
            assert len(new['premises']) == MIGRATION[name]['arity'], name
        else:
            assert (new['hash'], new['premises']) == (old['hash'], old['premises']), name
        assert old['proofs'].keys() == new['proofs'].keys(), name
        for pid, original in old['proofs'].items():
            updated = new['proofs'][pid]
            assert updated['steps'] <= original['steps'], name
            for key in ('axioms', 'valid'):
                assert updated[key] == original[key], (name, key)
            if name in affected:
                for key in ('direct_axioms', 'cites'):
                    assert updated[key] == original[key], (name, key)
            elif name not in MIGRATION:
                assert updated['step_hash'] == original['step_hash'], name


def test_preserves_old_proof_and_statement_boundaries(seeded_session):
    after = snapshot(seeded_session)
    # The value, preimage and composition theorems were added after the migration.
    added = {name for name, _, _ in (*RELATION_VALUES, *CLASS_VALUES, *PREIMAGE_STATEMENTS, *COMPOSITION_STATEMENTS)}
    assert after.keys() - BASELINE['theorems'].keys() == added
    assert_migration(BASELINE['theorems'], {name: after[name] for name in BASELINE['theorems']})


def test_old_and_new_statements_are_interderivable(fresh_seeded_session):
    builder = public_set_tools.Builder(fresh_seeded_session, 'premises-test')
    for name, migration in MIGRATION.items():
        old = BASELINE['theorems'][name]
        original = builder.parse(old['dss'])
        assert builder.fs.register(original).hash == old['hash'], name
        theorem = builder.ts.get_by_name(name)
        premises = tuple(builder.ps._tokens_for_formula(f.id) for _, f in builder.ts.list_premises(theorem.id))
        result = builder.ps._tokens_for_formula(theorem.conclusion_formula_id)

        builder.start()
        assumptions = tuple(map(builder.assume, premises))
        step = builder.cite(name, args=assumptions)
        for assumption in reversed(assumptions):
            step = builder.close(assumption, step)
        if migration['generalize']:
            builder.gen(step, 'a')
        proof = builder.finish(f'{name} old form', original)
        assert proof.status == 'verified', name
        assert builder.ts.get(proof.theorem_id).conclusion_formula.hash == old['hash'], name

        source, *arguments = builder.start((original, *premises))
        if migration['generalize']:
            source = builder.ui(source, builder.atom('a'))
        builder.apply(source, *arguments)
        proof = builder.finish(f'{name} new form', result, premises=(original, *premises))
        assert proof.status == 'verified', name


def test_builder_checks_arguments_and_kernel_still_rejects_wrong_order(fresh_seeded_session, monkeypatch):
    builder = public_set_tools.Builder(fresh_seeded_session, 'premises-test')
    name = 'ZF:非順序対の所属'
    theorem = builder.ts.get_by_name(name)
    premises = tuple(builder.ps._tokens_for_formula(f.id) for _, f in builder.ts.list_premises(theorem.id))
    conclusion = builder.ps._tokens_for_formula(theorem.conclusion_formula_id)
    first, second = builder.start(premises)
    with pytest.raises(ValidationError, match='Builder theorem premise mismatch'):
        builder.cite(name, args=(second, first))

    code = dedent(getsource(public_set_tools.Builder.cite))
    check = 'if instance != self.tokens(arg):'
    assert code.count(check) == 1
    namespace = vars(public_set_tools).copy()
    exec(code.replace(check, 'if False:'), namespace)
    monkeypatch.setattr(public_set_tools.Builder, 'cite', namespace['cite'])
    builder.cite(name, args=(second, first))
    with pytest.raises(ProofValidationError) as error:
        builder.finish('Incorrect premise order', conclusion, premises=premises)
    assert error.value.code == 'proof.arg_mismatch'


@pytest.mark.parametrize('name', [name for name, row in MIGRATION.items() if row['arity'] == 5])
def test_applicable_accepts_every_selection_order(fresh_seeded_session, name):
    dem = DemServices(fresh_seeded_session)
    target = dem.theorems.get_by_name(name)
    premise_ids = [f.id for _, f in dem.theorems.list_premises(target.id)]
    assert len(premise_ids) == 5
    draft = dem.theorems.register('Applicability example', target.conclusion_formula_id, premise_ids)
    proof = dem.proofs.create_proof(draft.id)
    for i in range(len(premise_ids)):
        dem.proofs.add_step(proof.id, PremiseStepInput(i))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dem_services] = lambda: dem

    async def exercise():
        for order in permutations(range(5)):
            query = urlencode({
                'proof_id': proof.id, 'goal_formula_id': target.conclusion_formula_id,
                'arg_step_ords': ','.join(map(str, order)), 'limit': 100,
            }).encode()

            async def application(scope, receive, send):
                await app({**scope, 'query_string': query}, receive, send)

            status, rows, _ = await asgi_request(application, 'GET', '/theorems/applicable')
            assert status == 200, (name, order, rows)
            assert target.id in [row['theorem']['id'] for row in rows], (name, order)

    asyncio.run(exercise())



@pytest.mark.parametrize('variant,error,message', [
    ('drop', ValueError, 'not enough values to unpack'),
    ('reverse', ValidationError, 'Builder MP mismatch'),
    ('old', ValueError, 'not enough values to unpack'),
])
def test_changed_migration_cannot_seed(seed_snapshot_factory, monkeypatch, variant, error, message):
    from dem.db.seeds import public_relation_proofs, public_relations
    from dem.db.seeds.public_unique_existence import seed_public_unique_existence

    statements = list(public_relation_proofs.STATEMENTS)
    name, premises, conclusion = statements[5]
    assert name == '包含:推移律'
    if variant == 'drop':
        premises = premises[:1]
    elif variant == 'reverse':
        premises = premises[::-1]
    else:
        premises, conclusion = (), BASELINE['theorems'][name]['dss']
    statements[5] = (name, premises, conclusion)
    monkeypatch.setattr(public_relation_proofs, 'STATEMENTS', statements)
    with seed_snapshot_factory.session('public_mk', 'sqlite') as session:
        seed_public_unique_existence(session)
        with pytest.raises(error, match=message):
            public_relations.seed_public_relations(session)

