"""Real API tutorial, display boundaries and anonymous reserved-tag probes."""
import asyncio
import json

import pytest
from sqlalchemy import select
from dem.db.models import Axiom, AxiomSystemMember, Proof, Theorem
from dem.types import AxiomStepInput, TheoremStepInput
from beta2_support import base_api, request as plain_request
from beta_http import asgi_request
from webapi.main import app
from test_beta_writes import reset_admission
from webapi import beta

from beta_fixture import base_phase
SEED_PHASE = base_phase()


def request(method, path, body=None):
    if '?' not in path:
        return plain_request(method, path, body)
    clean, _, query = path.partition('?')
    async def routed(scope, receive, send):
        await app(dict(scope, path=clean, raw_path=clean.encode(), query_string=query.encode()), receive, send)
    return asyncio.run(asgi_request(routed, method, clean, body, raise_app_exceptions=False))


def ok(method, path, body=None):
    status, value, _ = request(method, path, body)
    assert status in (200, 201, 204), (method, path, status, value)
    return value


@pytest.fixture
def hidden_example(base_api):
    with base_api.transaction() as dem:
        axiom = dem.session.scalar(select(Axiom).order_by(Axiom.id))
        hidden = dem.theorems.register("tutorial-hidden", axiom.formula_id, description="untrusted hidden text")
        tag = dem.tags.get_or_create("system:onboarding")
        dem.tags.attach("theorem", hidden.id, tag.id)
        proof = dem.proofs.create_proof(hidden.id)
        dem.proofs.add_step(proof.id, AxiomStepInput(axiom_id=axiom.id))
        dem.proofs.validate(proof.id)
        marker = dem.tags.get_or_create("system:rule")
        dem.tags.attach("theorem", hidden.id, marker.id)
        shown = dem.theorems.register("tutorial-visible-control", axiom.formula_id)
        shown_proof = dem.proofs.create_proof(shown.id)
        for _ in range(3):
            dem.proofs.add_step(shown_proof.id, TheoremStepInput(applied_proof_id=proof.id))
        dem.proofs.validate(shown_proof.id)
        dem.tags.attach("theorem", shown.id, marker.id)
        consumer = dem.theorems.register('tutorial-hidden-consumer', axiom.formula_id)
        dem.tags.attach('theorem', consumer.id, tag.id)
        consumer_proof = dem.proofs.create_proof(consumer.id)
        dem.proofs.add_step(consumer_proof.id, TheoremStepInput(applied_proof_id=shown_proof.id))
        dem.proofs.validate(consumer_proof.id)
        visible_consumer = dem.theorems.register('tutorial-visible-consumer', axiom.formula_id)
        visible_consumer_proof = dem.proofs.create_proof(visible_consumer.id)
        dem.proofs.add_step(visible_consumer_proof.id, TheoremStepInput(applied_proof_id=shown_proof.id))
        dem.proofs.validate(visible_consumer_proof.id)
        note = dem.explorations.create('tutorial-note', [])
        dem.proofs.add_step(note.proof.id, TheoremStepInput(applied_proof_id=proof.id))
        member = dem.session.scalar(select(AxiomSystemMember).where(AxiomSystemMember.axiom_id == axiom.id))
        return dict(hidden=hidden.id, public_id=hidden.public_id, proof=proof.id, shown=shown.id,
                    shown_proof=shown_proof.id, consumer=visible_consumer.id, note=note.theorem.public_id, formula=axiom.formula_id, axiom=axiom.id,
                    system=member.axiom_system_id, tag=tag.id)


@pytest.mark.parametrize('surface', ['list', 'page', 'search', 'tags', 'tags-page', 'rules', 'applicable', 'applicable-one', 'axiom-used', 'theorem-used', 'graph', 'system', 'formula-names', 'exploration-graph'])
def test_tutorial_discovery_surfaces(hidden_example, surface):
    e = hidden_example
    paths = dict(list='/theorems', page='/theorems?limit=500', search='/theorems?search=tutorial', tags='/tags', **{'tags-page': '/tags?limit=500'},
                 rules='/theorems/rules', **{'applicable-one': f"/theorems/applicable?goal_formula_id={e['formula']}&limit=1"}, applicable=f"/theorems/applicable?goal_formula_id={e['formula']}&limit=100",
                 **{'axiom-used': f"/axioms/{e['axiom']}/used-in-theorems",
                    'theorem-used': f"/theorems/{e['shown']}/used-in-theorems", 'graph': f"/proofs/{e['shown_proof']}/direct-dependencies",
                    'exploration-graph': f"/explorations/{e['note']}/steps/0/dependencies",
                    'system': f"/axiom-systems/{e['system']}/theorems", 'formula-names': f"/formulas/{e['formula']}/named-conclusions"})
    value = ok('GET', paths[surface])
    assert 'tutorial-hidden' not in json.dumps(value)
    if surface == 'applicable-one':
        assert len(value) == 1
    if surface in {'tags', 'tags-page'}:
        assert 'system:onboarding' not in json.dumps(value)
    if surface == 'graph':
        assert value['lemmas'] == [] and value['applied_proofs'] == {}
    if surface == 'theorem-used':
        assert e['consumer'] in {row['id'] for row in value}
    if surface in {'list', 'page', 'search', 'rules', 'system'}:
        assert e['shown'] in {row['id'] for row in value}


def test_counts_exclude_hidden_theorems_proofs_steps_and_dependency_targets(base_api):
    before = ok('GET', '/stats')
    with base_api.transaction() as dem:
        axiom = dem.session.scalar(select(Axiom).order_by(Axiom.id))
        hidden = dem.theorems.register('tutorial-count-hidden', axiom.formula_id)
        tag = dem.tags.get_or_create('system:onboarding')
        dem.tags.attach('theorem', hidden.id, tag.id)
        proof = dem.proofs.create_proof(hidden.id)
        dem.proofs.add_step(proof.id, AxiomStepInput(axiom_id=axiom.id))
        dem.proofs.validate(proof.id)
        shown = dem.theorems.register('tutorial-count-visible', axiom.formula_id)
        visible_proof = dem.proofs.create_proof(shown.id)
        dem.proofs.add_step(visible_proof.id, TheoremStepInput(applied_proof_id=proof.id))
        dem.proofs.validate(visible_proof.id)
    after = ok('GET', '/stats')
    for key in ('theorem_count', 'proven_theorem_count', 'verified_proof_count', 'proof_step_count'):
        assert after[key] == before[key] + 1
    assert after['dependency_count'] == before['dependency_count']


@pytest.mark.parametrize('enabled', [False, True])
def test_direct_urls_formula_interning_and_mathematical_use_stay_available(base_api, hidden_example, monkeypatch, enabled):
    reset_admission(monkeypatch, enabled)
    e = hidden_example
    assert ok('GET', f"/theorems/{e['public_id']}")['id'] == e['hidden']
    assert ok('GET', '/theorems/by-name/tutorial-hidden')['id'] == e['hidden']
    assert ok('GET', f"/proofs/{e['proof']}")['status'] == 'verified'
    detail = ok('GET', f"/formulas/{e['formula']}")
    assert ok('POST', '/formulas', {'tokens': detail['tokens']})['id'] == e['formula']
    assert e['formula'] in {row['id'] for row in ok('GET', '/formulas?limit=500')}
    printed = ok('POST', '/formulas/print', {'tokens': detail['tokens']})
    found = ok('POST', '/formulas/search', {'pattern': printed['text'], 'limit': 100})
    assert e['formula'] in {row['formula_id'] for row in found['items']}
    # Explicit mathematical references are not discovery candidates and must work.
    theorem = ok('POST', '/theorems', dict(name='tutorial-explicit-use', conclusion_formula_id=e['formula']))
    proof = ok('POST', '/proofs', dict(theorem_id=theorem['id']))
    suggestion = ok('POST', f"/proofs/{proof['id']}/steps/suggest", dict(kind='theorem', applied_theorem_id=e['hidden']))
    assert suggestion['applied_proof_id'] == e['proof']
    assert ok('POST', f"/proofs/{proof['id']}/steps/suggest-backward", dict(kind='theorem', applied_theorem_id=e['hidden'], goal_tokens=detail['tokens']))['candidates']
    ok('POST', f"/proofs/{proof['id']}/steps", dict(kind='theorem', applied_proof_id=e['proof']))
    assert ok('POST', f"/proofs/{proof['id']}/validate")['status'] == 'verified'
    assert ok('GET', f"/proofs/{proof['id']}/is-valid-in-system/{e['system']}")['is_subset'] is True
    # Hidden content is still shared/editable, not secret or moderation-safe.
    assert ok('PATCH', f"/theorems/{e['hidden']}/description", {'description': 'untrusted updated text'})['description'] == 'untrusted updated text'


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('tag_name', ['system:onboarding', 'system:exploration', 'ordinary-topic'])
def test_beta_reserved_tag_accept_reject_matrix(base_api, monkeypatch, enabled, tag_name):
    reset_admission(monkeypatch, enabled)
    with base_api.transaction() as dem:
        axiom = dem.session.scalar(select(Axiom).order_by(Axiom.id))
        formula_id = axiom.formula_id
    tag = ok('POST', '/tags', {'name': tag_name})
    victim = ok('POST', '/theorems', dict(name='tutorial-tag-victim', conclusion_formula_id=formula_id))
    status, value, _ = request('POST', f"/theorems/{victim['id']}/tags", dict(tag_id=tag['id']))
    strict = enabled and tag_name.startswith('system:')
    assert status == (422 if strict else 200), value
    if strict:
        assert tag['id'] not in {item['id'] for item in ok('GET', f"/theorems/{victim['id']}")['tags']}
    status, value, _ = request('POST', '/theorems', dict(name='tutorial-tag-new', conclusion_formula_id=formula_id, tag_ids=[tag['id']]))
    strict_create = enabled and tag_name == 'system:exploration'
    assert status == (422 if strict_create else 201), value
    if strict_create:
        assert request('GET', '/theorems/by-name/tutorial-tag-new')[0] == 404
    if not strict_create and tag_name == 'system:onboarding':
        assert ok('POST', f"/theorems/{value['id']}/tags", dict(tag_id=tag['id']))['id'] == value['id']
    # Legitimate exploration creation uses its existing internal path.
    note = ok('POST', '/explorations', {'name': 'tutorial-real-exploration', 'premise_formula_ids': []})
    assert note['theorem']['id']


def test_beta_nine_operation_script_reaches_verified_under_original_limits(base_api, monkeypatch):
    reset_admission(monkeypatch, True)
    # Freeze admission time so even very fast execution gets no token refill.
    monkeypatch.setattr(beta.runtime, 'clock', lambda: 1000)
    with base_api.session() as dem:
        symbols = list(dem.symbols.list_all())
        predicate = next(s for s in symbols if s.name == 'φ¹')
        variable = next(s for s in symbols if s.symbol_type.name == '項型自由変数記号')
    context = dict(P=predicate.id, x=variable.id)
    records = []
    def call(method, path, body=None):
        value = ok(method, path, body)
        records.append((method, path))
        return value
    goal = call('POST', '/formulas/parse', {'text': 'forall x. P(x) -> P(x)', 'context': {'P': predicate.id}})
    formula = call('POST', '/formulas', {'tokens': goal['tokens']})
    tag = call('POST', '/tags', {'name': 'system:onboarding'})
    theorem = call('POST', '/theorems', dict(name='tutorial-real-nine', conclusion_formula_id=formula['id'], tag_ids=[tag['id']], remarks=json.dumps({'phase1': {'variables': {'x': variable.id}}})))
    proof = call('POST', '/proofs', {'theorem_id': theorem['id']})
    for name, text in [('hilbert_k', 'P(x) -> ((P(x) -> P(x)) -> P(x))'),
                       ('hilbert_k', 'P(x) -> (P(x) -> P(x))'),
                       ('hilbert_s', '(P(x) -> ((P(x) -> P(x)) -> P(x))) -> ((P(x) -> (P(x) -> P(x))) -> (P(x) -> P(x)))')]:
        parsed = call('POST', '/formulas/parse', dict(text=text, context=context))
        axiom = call('GET', '/axioms/by-name/' + name)
        suggestion = call('POST', f"/proofs/{proof['id']}/steps/suggest", dict(kind='axiom', axiom_id=axiom['id'], goal_tokens=parsed['tokens']))
        assert suggestion['undetermined'] == []
        call('POST', f"/proofs/{proof['id']}/steps", dict(kind='axiom', axiom_id=axiom['id'], subst=suggestion['subst']))
    call('POST', f"/proofs/{proof['id']}/steps", dict(kind='mp', antecedent_step_ord=0, implication_step_ord=2))
    call('POST', f"/proofs/{proof['id']}/steps", dict(kind='mp', antecedent_step_ord=1, implication_step_ord=3))
    call('POST', f"/proofs/{proof['id']}/steps", dict(kind='gen', body_step_ord=4, gen_variable_symbol_id=variable.id))
    assert call('POST', f"/proofs/{proof['id']}/validate")['status'] == 'verified'
    writes = [(m,p) for m,p in records if m == 'POST' and p != '/formulas/parse']
    heavy = [(m,p) for m,p in records if p.endswith('/suggest') or p.endswith('/validate')]
    assert len(writes) == 14 and len(heavy) == 4
    admission = next(iter(beta.runtime.clients.values()))
    assert admission.buckets['write_minute'][0] == 6
    assert admission.buckets['heavy'][0] == 6


def test_invalid_proof_rejected_with_or_without_visibility_tag(base_api, monkeypatch):
    reset_admission(monkeypatch, True)
    with base_api.transaction() as dem:
        axioms = list(dem.session.scalars(select(Axiom).order_by(Axiom.id).limit(2)))
        tag = dem.tags.get_or_create('system:onboarding')
        ids = [(a.id, a.formula_id) for a in axioms]
        tag_id = tag.id
    for hidden in (False, True):
        theorem = ok('POST', '/theorems', dict(name='tutorial-reject-' + str(hidden), conclusion_formula_id=ids[0][1], tag_ids=[tag_id] if hidden else []))
        proof = ok('POST', '/proofs', dict(theorem_id=theorem['id']))
        ok('POST', f"/proofs/{proof['id']}/steps", dict(kind='axiom', axiom_id=ids[1][0]))
        status, body, _ = request('POST', f"/proofs/{proof['id']}/validate")
        assert status == 422 and body.get('code') not in {'beta.rate_limited', 'beta.busy'}
