"""Independent boundaries for the public equivalence, set and class packages."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from dem.db.models import (Base, Axiom, AxiomSystem, AxiomSystemMember, Definition,
                           Package, PackageRelease, Proof, Symbol, Theorem)
from dem.db.seeds import seed_public_equivalences, seed_all
from dem.db.seeds.public_catalog import PACKAGE_ENTITIES
from dem.db.seeds.public_equivalence import seed_public_equivalence
from dem.db.seeds.public_zfc import seed_public_zfc
from dem.db.seeds.public_mk import seed_public_mk
from dem.db.seeds.public_packages import assign_public_releases
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.services.symbol import SymbolService
from dem.services.package import publish_release, check_release_dependencies
from dem.errors import ProofValidationError
from dem.types import AxiomStepInput, SymbolTypeName

SEED_PHASE = 'public_mk'
MODELS = (Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof)
SYSTEMS = ('hilbert_core','hilbert_classical','直観主義論理','古典論理',
           '直観主義論理（同値つき）','古典論理（同値つき）','ZF','ZFC','MK')


@pytest.fixture
def empty_session(tmp_path):
    engine=create_engine('sqlite+pysqlite:///'+str(tmp_path/'empty.db'))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session: yield session
    finally: engine.dispose()


def assert_ownership(session):
    for model in MODELS:
        rows = list(session.scalars(select(model)))
        expected = {}
        for phase in PACKAGE_ENTITIES.values():
            from dem.db.seeds.public_packages import package_name
            release = session.scalar(select(PackageRelease).join(Package).where(Package.name == package_name(phase['package'])))
            for pid in phase['entities'][model.__tablename__]: expected[pid] = release.id
        assert set(expected) == {r.public_id for r in rows}
        assert all(r.release_id == expected[r.public_id] for r in rows)


def test_shared_identities_and_requested_statements(fresh_seeded_session):
    s=fresh_seeded_session; fs=FormulaService(s)
    spec=json.loads((Path(__file__).parent/'fixtures/public-zfc-mk-spec.json').read_text(encoding='utf-8'))
    for expected in spec['symbols']:
        assert SymbolService(s).get_by_name(expected['name']).public_id==expected['actual']
    for expected in spec['axioms']:
        axiom=AxiomService(s).get_by_name(expected['name'])
        assert axiom.public_id==expected['expected_id']
        assert fs.register(fs.parse_text(expected['dss'])[0]).hash==expected['expected_hash']
        assert fs.register(fs.parse_text(expected['dss'])[0]).id==axiom.formula_id
    for name,text in spec['statements'].items():
        theorem=TheoremService(s).get_by_name(name)
        assert fs.register(fs.parse_text(text)[0]).id==theorem.conclusion_formula_id


def test_proposition_variable_attributes_match(fresh_seeded_session):
    s = fresh_seeded_session
    symbols = SymbolService(s)
    type_id = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id
    variables = list(s.scalars(select(Symbol).where(Symbol.symbol_type_id == type_id)))
    assert variables and all(not variable.is_primitive for variable in variables)
    assert [symbols.get_by_name(name).latex_template for name in ('φ¹', 'φ²', 'φ³')] == [None, None, None]


def test_ownership_dependency_closure_and_freeze(fresh_seeded_session):
    s = fresh_seeded_session
    assert_ownership(s)
    releases = list(s.scalars(select(PackageRelease).order_by(PackageRelease.id)))
    assert len(releases) == 6
    for r in releases:
        assert not check_release_dependencies(s,r.id)
        publish_release(s,r.id)
    for model in MODELS:
        for row in s.scalars(select(model)):
            with pytest.raises(IntegrityError):
                with s.begin_nested(): s.execute(update(model).where(model.id == row.id).values(name='freeze mutation'))


def test_all_new_proofs_in_all_systems(fresh_seeded_session):
    s = fresh_seeded_session; ps = ProofService(s); axs = AxiomService(s)
    new = [t for t in s.scalars(select(Theorem)) if t.name.startswith(('ZF:','MK:'))]
    assert len(new) == 24
    for theorem in new:
        proofs = ps.list_for_theorem(theorem.id)
        assert len(proofs) == 1 and proofs[0].status == 'verified' and theorem.status == 'proven'
        assert len(ps.list_steps(proofs[0].id)) <= 200
        expected = ([False]*8+[True] if theorem.name.startswith('MK:') else
                    [False,False]+[True]*7 if theorem.name == 'ZF:対の共通成分消去' else [False]*6+[True]*3)
        assert [ps.is_valid_in_system(proofs[0].id,axs.get_system_by_name(n).id) for n in SYSTEMS] == expected, theorem.name
        for step in ps.list_steps(proofs[0].id):
            if step.applied_proof_id:
                cited = ps.get(step.applied_proof_id)
                assert TheoremService(s).get(cited.theorem_id).name.startswith(('ZF:','MK:'))


def test_system_members(fresh_seeded_session):
    s=fresh_seeded_session; ax=AxiomService(s)
    members=[]
    for name in SYSTEMS:
        sid=ax.get_system_by_name(name).id
        members.append(set(s.scalars(select(AxiomSystemMember.axiom_id).where(AxiomSystemMember.axiom_system_id==sid))))
    assert list(map(len,members)) == [7,8,18,19,21,22,33,34,36]
    equiv={ax.get_by_name(n).id for n in ('同値導入公理','同値除去公理（左）','同値除去公理（右）')}
    assert members[4]==members[2]|equiv and members[5]==members[3]|equiv
    assert members[7]==members[6]|{ax.get_by_name('ZF選択公理').id}
    assert members[8]==members[7]|{ax.get_by_name(n).id for n in ('MK類内包公理図式','MK類外延性公理')}


def test_completed_packages_use_select_only(fresh_seeded_session):
    s=fresh_seeded_session; s.connection(); statements=[]
    def record(conn,cursor,statement,parameters,context,many): statements.append(statement.lstrip().split()[0].upper())
    event.listen(s.get_bind(),'before_cursor_execute',record)
    try:
        seed_public_equivalence(s); seed_public_zfc(s); seed_public_mk(s); assign_public_releases(s)
    finally: event.remove(s.get_bind(),'before_cursor_execute',record)
    assert statements and set(statements)=={'SELECT'}


def test_mutation_replacing_axiom_is_rejected(fresh_seeded_session):
    s=fresh_seeded_session; ps=ProofService(s); fs=FormulaService(s)
    theorem=TheoremService(s).get_by_name('ZF:非順序対の集合性')
    original=ps.list_for_theorem(theorem.id)[0]; specs=ps.reconstruct_steps(original.id)
    replacement=AxiomService(s).get_by_name('hilbert_eq_refl')
    specs[0]=(AxiomStepInput(replacement.id),ps.compute_substituted_tokens(replacement.formula_id,AxiomStepInput(replacement.id).subst))
    mutated=ps.create_proof(theorem.id,name='public axiom mutation')
    with pytest.raises(ProofValidationError):
        for step,tokens in specs: ps.add_step(mutated.id,step,fs.register(tokens).id)
        ps.validate(mutated.id)
    assert mutated.status!='verified'


def test_mutation_removing_zfc_axiom_changes_validity(fresh_seeded_session):
    s=fresh_seeded_session; ax=AxiomService(s); ps=ProofService(s)
    zfc=ax.get_system_by_name('ZFC'); theorem=TheoremService(s).get_by_name('ZF:非順序対の集合性')
    proof=ps.list_for_theorem(theorem.id)[0]
    assert ps.is_valid_in_system(proof.id,zfc.id)
    ax.remove_from_system(zfc.id,ax.get_by_name('ZF対公理').id)
    assert not ps.is_valid_in_system(proof.id,zfc.id)


def test_mutation_missing_catalog_owner_fails(fresh_seeded_session,monkeypatch):
    s=fresh_seeded_session
    import dem.db.seeds.public_packages as packages
    broken=copy.deepcopy(PACKAGE_ENTITIES)
    pid=broken['public_mk']['entities']['axiom'].pop()
    monkeypatch.setattr(packages,'PACKAGE_ENTITIES',broken)
    row=s.scalar(select(Axiom).where(Axiom.public_id==pid)); row.release_id=None; s.flush()
    assign_public_releases(s)
    with pytest.raises(AssertionError): assert_ownership(s)


def test_existing_digest_members_and_validity_unchanged(empty_session):
    s=empty_session; seed_public_equivalences(s)
    ps=ProofService(s); axs=AxiomService(s)
    proofs=list(s.scalars(select(Proof))); systems=list(s.scalars(select(AxiomSystem)))
    validity={(p.id,a.id):ps.is_valid_in_system(p.id,a.id) for p in proofs for a in systems}
    members=set(s.execute(select(AxiomSystemMember.axiom_system_id,AxiomSystemMember.axiom_id)))
    old=list(s.scalars(select(PackageRelease).order_by(PackageRelease.id)))
    digests={r.id:publish_release(s,r.id).content_digest for r in old}
    seed_public_zfc(s); seed_public_mk(s); assign_public_releases(s)
    assert {r.id:publish_release(s,r.id).content_digest for r in old}==digests
    assert {(p.id,a.id):ps.is_valid_in_system(p.id,a.id) for p in proofs for a in systems}==validity
    assert set(s.execute(select(AxiomSystemMember.axiom_system_id,AxiomSystemMember.axiom_id).where(
        AxiomSystemMember.axiom_system_id.in_([a.id for a in systems]))))==members
