"""Adversarial API inputs, and legitimate experiments in user axiom systems."""
import pytest
from sqlalchemy import func, select

from dem.db.models import Base, Formula, FormulaToken, SymbolType, Theorem, Proof, ProofStep
from dem.types import SymbolTypeName
from beta2_support import base_api, published_api, request, digests, report
from test_beta_writes import accepted, reset_admission

from beta_fixture import base_phase
SEED_PHASE = base_phase()


def counts(api):
    with api.session() as dem:
        return tuple(dem.session.scalar(select(func.count()).select_from(model)) for model in (Formula, FormulaToken, ProofStep))


def vocabulary(api):
    with api.session() as dem:
        types = {t.name: t.id for t in dem.session.scalars(select(SymbolType))}
        bottom = dem.symbols.get_by_name("⊥").id
        implication = dem.symbols.get_by_role("implication").id
    symbols = {}
    for name, kind, arity in (("test-P", SymbolTypeName.FREE_PROP_VAR, 0), ("test-Q", SymbolTypeName.FREE_PROP_VAR, 0),
                              ("test-x", SymbolTypeName.FREE_TERM_VAR, 0), ("test-R", SymbolTypeName.PREDICATE, 1)):
        symbols[name] = accepted("POST", "/symbols", {"name": name, "symbol_type_id": types[kind.value], "arity": arity})["id"]
    def formula(ids):
        return accepted("POST", "/formulas", {"tokens": [{"symbol_id": id} for id in ids]})["id"]
    p, q, x, r = (symbols[name] for name in ("test-P", "test-Q", "test-x", "test-R"))
    return dict(p=p, q=q, x=x, r=r, imp=implication, bottom=bottom,
                pf=formula([p]), qf=formula([q]), xf=formula([x]), rf=formula([r, x]),
                implication=formula([implication, p, q]), bottomf=formula([bottom]))


@pytest.mark.parametrize("enabled", [False, True])
def test_malformed_formulas_are_atomic(published_api, monkeypatch, enabled):
    api = published_api
    v = vocabulary(api)
    before = digests(api)
    cases = {
        "arity": [{"symbol_id": v["imp"]}, {"symbol_id": v["p"]}],
        "type": [{"symbol_id": v["imp"]}, {"symbol_id": v["x"]}, {"symbol_id": v["q"]}],
        "unbound": [{"de_bruijn_index": 0}],
        "empty": [],
        "missing_symbol": [{"symbol_id": 2147483647}],
    }
    rows = []
    for case, tokens in cases.items():
        reset_admission(monkeypatch, enabled)
        start = counts(api)
        status, body, _ = request("POST", "/formulas", {"tokens": tokens})
        assert 400 <= status < 500, ("STOP: invalid formula accepted", case, tokens, status, body)
        assert counts(api) == start and digests(api) == before
        rows.append(dict(case=case, status=status, response=body))
    report(f"bad-formulas-{api.engine.dialect.name}-{enabled}", rows)


@pytest.mark.parametrize("enabled", [False, True])
def test_invalid_proofs_never_verify(published_api, monkeypatch, enabled):
    api = published_api
    v = vocabulary(api)
    user_axiom = accepted("POST", "/axioms", {"name": "test-substitution-axiom", "formula_id": v["pf"]})
    draft = accepted("POST", "/theorems", {"name": "test-draft-citation", "conclusion_formula_id": v["bottomf"]})
    draft_proof = accepted("POST", "/proofs", {"theorem_id": draft["id"]})
    cases = {
        "mp_mismatch": ([{"kind": "premise", "premise_ord": 1}, {"kind": "premise", "premise_ord": 2}],
                        {"kind": "mp", "antecedent_step_ord": 0, "implication_step_ord": 1}),
        "missing_step": ([], {"kind": "mp", "antecedent_step_ord": -1, "implication_step_ord": -1}),
        "future_step": ([], {"kind": "mp", "antecedent_step_ord": 1, "implication_step_ord": 2}),
        "axiom_substitution": ([], {"kind": "axiom", "axiom_id": user_axiom["id"], "subst": {
            "prop_substs": [{"source_symbol_id": v["p"], "body_formula_id": v["xf"]}]}}),
        "premise_range": ([], {"kind": "premise", "premise_ord": 99}),
        "draft_citation": ([], {"kind": "theorem", "applied_proof_id": draft_proof["id"]}),
        "gen_in_premise": ([{"kind": "premise", "premise_ord": 3}],
                           {"kind": "gen", "body_step_ord": 0, "gen_variable_symbol_id": v["x"]}),
        "intro_not_assumption": ([{"kind": "premise", "premise_ord": 0}],
                                 {"kind": "imp_intro", "assumption_step_ord": 0, "body_step_ord": 0}),
    }
    before = digests(api)
    rows = []
    for case, (prefix, invalid) in cases.items():
        reset_admission(monkeypatch, enabled)
        theorem = accepted("POST", "/theorems", {"name": "invalid-" + case, "conclusion_formula_id": v["bottomf"],
            "premise_formula_ids": [v["pf"], v["qf"], v["implication"], v["rf"]]})
        proof = accepted("POST", "/proofs", {"theorem_id": theorem["id"]})
        path = f"/proofs/{proof['id']}"
        for step in prefix:
            accepted("POST", path + "/steps", step)
        start = counts(api)
        status, body, _ = request("POST", path + "/steps", invalid)
        assert 400 <= status < 500, (case, invalid, status, body)
        assert counts(api) == start
        validate_status, validate_body, _ = request("POST", path + "/validate")
        assert 400 <= validate_status < 500, ("STOP: invalid proof verified", case, validate_status, validate_body)
        with api.session() as dem:
            assert dem.session.get(Proof, proof["id"]).status != "verified"
            assert dem.session.get(Theorem, theorem["id"]).status != "proven"
        assert digests(api) == before
        rows.append(dict(case=case, add_status=status, add_response=body, validate_status=validate_status, validate_response=validate_body))
    report(f"bad-proofs-{api.engine.dialect.name}-{enabled}", rows)


@pytest.mark.parametrize("enabled", [False, True])
def test_status_fields_cannot_promote(published_api, monkeypatch, enabled):
    api = published_api
    v = vocabulary(api)
    reset_admission(monkeypatch, enabled)
    before = digests(api)
    theorem = accepted("POST", "/theorems", {"name": "status-injection", "conclusion_formula_id": v["bottomf"], "status": "proven"})
    proof = accepted("POST", "/proofs", {"theorem_id": theorem["id"], "status": "verified"})
    accepted("PATCH", f"/theorems/{theorem['id']}/description", {"description": "still a conjecture", "status": "proven"})
    # Proofs have no update route. An extra status in a step cannot promote one.
    accepted("POST", f"/proofs/{proof['id']}/steps", {"kind": "assumption", "conclusion_formula_id": v["bottomf"], "status": "verified"})
    with api.session() as dem:
        assert dem.session.get(Theorem, theorem["id"]).status == "conjecture"
        assert dem.session.get(Proof, proof["id"]).status == "draft"
    status, body, _ = request("POST", f"/proofs/{proof['id']}/validate")
    assert 400 <= status < 500, ("STOP: open assumption verified", status, body)
    assert digests(api) == before


@pytest.mark.parametrize("enabled", [False, True])
def test_contradictory_user_system_does_not_change_base(published_api, monkeypatch, enabled):
    api = published_api
    v = vocabulary(api)
    reset_admission(monkeypatch, enabled)
    with api.session() as dem:
        members = Base.metadata.tables["axiom_system_member"]
        base_system = dem.session.scalar(select(members.c.axiom_system_id).distinct().order_by(members.c.axiom_system_id))
    before = digests(api)
    axiom = accepted("POST", "/axioms", {"name": "user-bottom", "formula_id": v["bottomf"]})
    system = accepted("POST", "/axiom-systems", {"name": "user-contradictory-system"})
    accepted("POST", f"/axiom-systems/{system['id']}/members", {"axiom_id": axiom["id"]})
    theorem = accepted("POST", "/theorems", {"name": "user-bottom-theorem", "conclusion_formula_id": v["bottomf"]})
    proof = accepted("POST", "/proofs", {"theorem_id": theorem["id"]})
    accepted("POST", f"/proofs/{proof['id']}/steps", {"kind": "axiom", "axiom_id": axiom["id"]})
    assert accepted("POST", f"/proofs/{proof['id']}/validate")["status"] == "verified"
    user_valid = accepted("GET", f"/proofs/{proof['id']}/is-valid-in-system/{system['id']}")
    base_valid = accepted("GET", f"/proofs/{proof['id']}/is-valid-in-system/{base_system}")
    assert user_valid == {"is_subset": True} and base_valid == {"is_subset": False}
    status, body, _ = request("POST", f"/axiom-systems/{base_system}/members", {"axiom_id": axiom["id"]})
    assert status == 409, (status, body)
    assert digests(api) == before
    with api.session() as dem:
        assert dem.session.get(Theorem, theorem["id"]).status == "proven"
    report(f"contradiction-{api.engine.dialect.name}-{enabled}", dict(proof_status="verified", theorem_status="proven", user_system=user_valid, base_system=base_valid, base_member_status=status))
