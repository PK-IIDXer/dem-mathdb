"""User-specified elementary logic, verified through unchanged kernel services."""
import hashlib
import json

import pytest
from sqlalchemy import event, select, func, update
from sqlalchemy.exc import IntegrityError

from dem.db.models import (
    Axiom, AxiomSystem, AxiomSystemMember, Definition, Proof, ProofStep,
    PackageRelease, Symbol, Theorem,
)
from dem.db.seeds import seed_all
from dem.db.seeds.public_catalog import PACKAGE_ENTITIES
from dem.db.seeds.public_natural_deduction import seed_public_natural_deduction
from dem.errors import ProofValidationError, ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.theorem import TheoremService
from dem.services.symbol import SymbolService
from dem.types import AxiomStepInput
from dem.types import Token

SEED_PHASE = "public_natural_deduction"

# An independent expected matrix, not generated from the seed's constants.
EXPECTED = {
    "含意除去": (True, True, True, True, 3),
    "矛盾除去": (False, False, True, True, 3),
    "否定導入": (False, False, True, True, 3),
    "否定除去": (False, False, True, True, 5),
    "連言導入": (False, False, True, True, 5),
    "連言除去（左）": (False, False, True, True, 3),
    "連言除去（右）": (False, False, True, True, 3),
    "選言導入（左）": (False, False, True, True, 3),
    "選言導入（右）": (False, False, True, True, 3),
    "選言除去": (False, False, True, True, 7),
    "全称除去": (True, True, True, True, 3),
    "存在導入": (False, False, True, True, 3),
    "存在除去": (False, False, True, True, 5),
    "等号代入": (True, True, True, True, 5),
    "二重否定導入": (False, False, True, True, 7),
    "対偶": (False, False, True, True, 10),
    "無矛盾律": (False, False, True, True, 9),
    "連言の交換": (False, False, True, True, 7),
    "選言の交換": (False, False, True, True, 11),
    "ド・モルガン": (False, False, True, True, 17),
    "二重否定除去": (False, False, False, True, 13),
    "排中律": (False, False, False, True, 16),
}
SYSTEMS = ("hilbert_core", "hilbert_classical", "直観主義論理", "古典論理")
MODELS = (Symbol, Definition, Axiom, AxiomSystem, Theorem, Proof)


def test_all_statements_match_the_user_specification(fresh_seeded_session):
    session = fresh_seeded_session
    symbols, formulas = SymbolService(session), FormulaService(session)
    atom = lambda name: [Token(symbols.get_by_name(name).id)]
    op = lambda name, *args: [*atom(name), *(t for arg in args for t in arg)]
    P, Q, R, B = [atom(n) for n in ("φ", "ψ", "χ", "⊥")]
    I = lambda a, b: op("→", a, b)
    N = lambda a: op("¬", a)
    C = lambda a, b: op("∧", a, b)
    D = lambda a, b: op("∨", a, b)
    px, py, pt = [op("φ¹", atom(n)) for n in ("x", "y", "t")]
    bound = op("φ¹", [Token(de_bruijn_index=0)])
    every, some = op("∀", bound), op("∃", bound)
    ei = op("∀", I(bound, Q))
    equal = op("=", atom("x"), atom("y"))
    axioms = {
        "矛盾除去公理": I(B, P), "否定導入公理": I(I(P, B), N(P)), "否定除去公理": I(N(P), I(P, B)),
        "連言導入公理": I(P, I(Q, C(P, Q))), "連言除去公理（左）": I(C(P, Q), P), "連言除去公理（右）": I(C(P, Q), Q),
        "選言導入公理（左）": I(P, D(P, Q)), "選言導入公理（右）": I(Q, D(P, Q)),
        "選言除去公理": I(I(P, R), I(I(Q, R), I(D(P, Q), R))),
        "存在導入公理": I(pt, some), "存在除去公理": I(ei, I(some, Q)),
    }
    expected = {
        "含意除去": ((I(P, Q), P), Q), "矛盾除去": ((B,), P), "否定導入": ((I(P, B),), N(P)),
        "否定除去": ((N(P), P), B), "連言導入": ((P, Q), C(P, Q)),
        "連言除去（左）": ((C(P, Q),), P), "連言除去（右）": ((C(P, Q),), Q),
        "選言導入（左）": ((P,), D(P, Q)), "選言導入（右）": ((Q,), D(P, Q)),
        "選言除去": ((D(P, Q), I(P, R), I(Q, R)), R), "全称除去": ((every,), pt),
        "存在導入": ((pt,), some), "存在除去": ((some, ei), Q), "等号代入": ((equal, px), py),
        "二重否定導入": ((), I(P, N(N(P)))), "対偶": ((), I(I(P, Q), I(N(Q), N(P)))),
        "無矛盾律": ((), N(C(P, N(P)))), "連言の交換": ((), I(C(P, Q), C(Q, P))),
        "選言の交換": ((), I(D(P, Q), D(Q, P))), "ド・モルガン": ((), I(N(D(P, Q)), C(N(P), N(Q)))),
        "二重否定除去": ((), I(N(N(P)), P)), "排中律": ((), D(P, N(P))),
    }
    def tokens(formula_id):
        return [Token(t.symbol_id, t.de_bruijn_index) for t in formulas.get_tokens(formula_id)]
    for name, statement in axioms.items():
        axiom = AxiomService(session).get_by_name(name)
        assert tokens(axiom.formula_id) == statement
        assert "Hilbert coreから導出したものではなく" in axiom.description
    for name, (premises, conclusion) in expected.items():
        theorem = TheoremService(session).get_by_name(name)
        assert tokens(theorem.conclusion_formula_id) == conclusion
        from dem.db.models.theorem import TheoremPremise
        rows = session.scalars(select(TheoremPremise).where(TheoremPremise.theorem_id == theorem.id).order_by(TheoremPremise.ord))
        assert [tokens(row.formula_id) for row in rows] == list(premises)


@pytest.mark.parametrize("name", EXPECTED)
def test_each_proof_in_all_four_systems(fresh_seeded_session, name):
    session = fresh_seeded_session
    service = ProofService(session)
    theorem = TheoremService(session).get_by_name(name)
    proofs = service.list_for_theorem(theorem.id)
    assert theorem.status == "proven" and len(proofs) == 1
    proof = proofs[0]
    assert proof.status == "verified"
    assert len(service.list_steps(proof.id)) == EXPECTED[name][4]
    for system, expected in zip(SYSTEMS, EXPECTED[name][:4], strict=True):
        assert service.is_valid_in_system(proof.id, AxiomService(session).get_system_by_name(system).id) is expected


def test_catalog_preserves_every_existing_public_identity_and_owns_all_rows(fresh_seeded_session):
    old = {key: PACKAGE_ENTITIES[key] for key in ("public_core", "public_demo")}
    # Pinned to the exact catalog at public 11.11 (all six kinds, both packages).
    assert hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest() == "45cceedd4b006e56d400d6c88f523f8cab08c2284b0a07a89c1886b4a315ba27"
    session = fresh_seeded_session
    new = PACKAGE_ENTITIES[SEED_PHASE]["entities"]
    assert {kind: len(ids) for kind, ids in new.items()} == {
        "symbol": 0, "definition": 0, "axiom": 11, "axiom_system": 2, "theorem": 22, "proof": 22}
    for model in MODELS:
        kind = model.__tablename__
        catalogued = {pid for phase in PACKAGE_ENTITIES.values() for pid in phase["entities"][kind]}
        rows = list(session.scalars(select(model)))
        assert {row.public_id for row in rows} == catalogued
        for phase in PACKAGE_ENTITIES.values():
            expected_release = session.scalar(select(PackageRelease).where(
                PackageRelease.manifest["package"].as_string() == {
                    "public-core": "dem.public.logic", "public-demo": "dem.public.demos",
                    "public-natural-deduction": "dem.public.natural_deduction"}[phase["package"]]))
            for row in rows:
                if row.public_id in phase["entities"][kind]:
                    assert expected_release is not None and row.release_id == expected_release.id


def test_system_members_are_exact_and_old_systems_unchanged(fresh_seeded_session):
    session = fresh_seeded_session
    service = AxiomService(session)
    members = []
    for name in SYSTEMS:
        system = service.get_system_by_name(name)
        members.append(set(session.scalars(select(AxiomSystemMember.axiom_id).where(
            AxiomSystemMember.axiom_system_id == system.id))))
    peirce = service.get_by_name("hilbert_peirce").id
    assert len(members[0]) == 7 and members[1] == members[0] | {peirce}
    new_ids = set(session.scalars(select(Axiom.id).where(Axiom.public_id.in_(
        PACKAGE_ENTITIES[SEED_PHASE]["entities"]["axiom"]))))
    assert len(new_ids) == 11 and members[2] == members[0] | new_ids
    assert members[3] == members[2] | {peirce}


def test_completed_seed_rebuilds_no_proofs(fresh_seeded_session):
    session = fresh_seeded_session
    # Start the fixture transaction (including PostgreSQL's SAVEPOINT) before recording seed SQL.
    session.connection()
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        seed_public_natural_deduction(session)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert set(statements) <= {"SELECT"}
    seed_all(session)
    assert session.scalar(select(func.count()).select_from(Proof)) == 28


def test_incomplete_seed_is_rejected(fresh_seeded_session):
    session = fresh_seeded_session
    # Extra unfinished content is detected without editing any verified proof.
    ProofService(session).create_proof(TheoremService(session).get_by_name("排中律").id, name="incomplete probe")
    with pytest.raises(ValidationError, match="Incomplete"):
        seed_public_natural_deduction(session)


def test_dne_has_the_supplied_thirteen_steps_and_no_theorem_citation(fresh_seeded_session):
    session = fresh_seeded_session
    service = ProofService(session)
    proof = service.list_for_theorem(TheoremService(session).get_by_name("二重否定除去").id)[0]
    steps = service.list_steps(proof.id)
    assert [s.step_kind for s in steps] == ["assumption", "axiom", "rule", "assumption",
        "axiom", "rule", "rule", "axiom", "rule", "rule", "axiom", "rule", "rule"]
    assert [s.axiom_id for s in steps if s.step_kind == "axiom"] == [
        AxiomService(session).get_by_name(name).id for name in
        ("否定除去公理", "否定導入公理", "矛盾除去公理", "hilbert_peirce")]
    for name, dependency in (("二重否定導入", "否定除去"), ("対偶", "否定除去"), ("排中律", "二重否定除去")):
        target = service.list_for_theorem(TheoremService(session).get_by_name(name).id)[0]
        cited = service.list_for_theorem(TheoremService(session).get_by_name(dependency).id)[0]
        assert cited.id in {s.applied_proof_id for s in service.list_steps(target.id)}


def test_mutation_replacing_peirce_breaks_dne_validation(fresh_seeded_session):
    session = fresh_seeded_session
    service = ProofService(session)
    theorem = TheoremService(session).get_by_name("二重否定除去")
    original = service.list_for_theorem(theorem.id)[0]
    specs = service.reconstruct_steps(original.id)
    replacement = AxiomService(session).get_by_name("hilbert_k")
    specs[10] = (AxiomStepInput(replacement.id), service.compute_substituted_tokens(replacement.formula_id, AxiomStepInput(replacement.id).subst))
    mutated = service.create_proof(theorem.id, name="Peirce replacement mutation")
    with pytest.raises(ProofValidationError) as failure:
        for step, tokens in specs:
            service.add_step(mutated.id, step, FormulaService(session).register(tokens).id)
        service.validate(mutated.id)
    assert failure.value.code == "proof.mp_antecedent_mismatch"
    assert mutated.status != "verified"


def test_mutation_removing_peirce_rejects_classical_theorems(fresh_seeded_session):
    session = fresh_seeded_session
    axioms = AxiomService(session)
    classical = axioms.get_system_by_name(SYSTEMS[3])
    axioms.remove_from_system(classical.id, axioms.get_by_name("hilbert_peirce").id)
    service = ProofService(session)
    for name in ("二重否定除去", "排中律"):
        proof = service.list_for_theorem(TheoremService(session).get_by_name(name).id)[0]
        assert not service.is_valid_in_system(proof.id, classical.id)


def test_publication_freezes_every_catalogued_entity(fresh_seeded_session):
    session = fresh_seeded_session
    from dem.services.package import publish_release
    for release in session.scalars(select(PackageRelease).order_by(PackageRelease.id)):
        publish_release(session, release.id)
    session.flush()
    for model in MODELS:
        ids = list(session.scalars(select(model.id)))
        for row_id in ids:
            with pytest.raises(IntegrityError):
                with session.begin_nested():
                    session.execute(update(model).where(model.id == row_id).values(name="frozen mutation"))
