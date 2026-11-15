"""Regression coverage for assigning proof steps to public lemma premises."""

import asyncio

import pytest
from fastapi import FastAPI

from beta_http import asgi_request
from dem.api import DemServices
from dem.errors import ValidationError
from dem.services.theorem import LemmaCandidate, rank_lemma_candidates
from dem.types import FormulaTypeName, PremiseStepInput, SymbolMeta, SymbolTypeName, TermSubst, TheoremStepInput, Token
from webapi.deps import dem_services
from webapi.routers.proofs import router

SEED_PHASE = "public_zfc"


def formula(dem, text):
    return dem.formulas.register(dem.formulas.parse_text(text)[0])


def open_proof(dem, name, goal, premises):
    theorem = dem.theorems.register(
        name, formula(dem, goal).id, [formula(dem, text).id for text in premises],
    )
    proof = dem.proofs.create_proof(theorem.id)
    for slot in range(len(premises)):
        dem.proofs.add_step(proof.id, PremiseStepInput(slot))
    return proof.id


@pytest.fixture
def equality_case(fresh_seeded_session):
    dem = DemServices(fresh_seeded_session)
    term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    dem.symbols.register("X", term_type.id, 0)
    lemma = dem.theorems.get_by_name("等号代入")
    proof_id = open_proof(dem, "equality argument order", "a ∈ X", ("∅ ∈ X", "∅ = a"))
    return dem, proof_id, lemma.id


@pytest.mark.parametrize(("ords", "slots"), [
    ((0, 1), (1, 0)),
    ((1, 0), (0, 1)),
    ((0,), (1,)),
    ((1,), (0,)),
])
def test_equality_argument_order(equality_case, ords, slots):
    dem, proof_id, lemma_id = equality_case
    candidates = dem.theorems.list_applicable(proof_id=proof_id, arg_step_ords=ords, limit=500)
    assert lemma_id in {item.id for item, _, _ in candidates}
    suggestion = dem.proofs.suggest_step(
        proof_id, kind="theorem", applied_theorem_id=lemma_id, arg_step_ords=ords,
    )
    assert suggestion["arg_slots"] == slots


def test_repeated_step_does_not_match_equality_substitution(equality_case):
    dem, proof_id, lemma_id = equality_case
    with pytest.raises(ValidationError) as caught:
        dem.proofs.suggest_step(
            proof_id, kind="theorem", applied_theorem_id=lemma_id, arg_step_ords=(0, 0),
        )
    assert caught.value.code == "proof.suggestion_no_match"


@pytest.mark.parametrize(("argument", "variable"), [("w", "t"), ("w", "a"), ("t", "t")])
def test_universal_elimination_preserves_free_variables(fresh_seeded_session, argument, variable):
    dem = DemServices(fresh_seeded_session)
    lemma = dem.theorems.get_by_name("全称除去")
    goal_text = f"{argument} ∈ {variable}"
    proof_id = open_proof(dem, "universal elimination goal", goal_text, [f"∀ z. z ∈ {variable}"])
    goal_tokens = dem.formulas.parse_text(goal_text)[0]
    suggestion = dem.proofs.suggest_step(
        proof_id, kind="theorem", applied_theorem_id=lemma.id, arg_step_ords=(0,), goal_tokens=goal_tokens,
    )
    assert suggestion["conclusion_tokens"] == goal_tokens
    subst = suggestion["subst"]
    source = dem.symbols.get_by_name("t").id
    assert subst.term_substs[0] == TermSubst(source, formula(dem, argument).id)
    if variable == "t" and argument != "t":
        _, alias = subst.term_substs
        body, = subst.prop_substs
        assert alias.source_symbol_id not in {
            source, dem.symbols.get_by_name(argument).id, *body.formal_param_symbol_ids,
        }
        assert alias.target_formula_id == formula(dem, "t").id
        assert dem.formulas.get_tokens(body.body_formula_id)[-1].symbol_id == alias.source_symbol_id
    else:
        assert len(subst.term_substs) == 1
    step = dem.proofs.add_step(proof_id, TheoremStepInput(suggestion["applied_proof_id"], subst, (0,)))
    assert step.conclusion_formula_id == formula(dem, goal_text).id
    dem.proofs.validate(proof_id)
    assert dem.proofs.get(proof_id).status == "verified"


def test_positional_match_precedes_higher_scoring_reordered_match():
    atom = SymbolMeta(0, SymbolTypeName.LOGICAL, FormulaTypeName.PROPOSITION, None, False)
    selected, other = (Token(symbol_id=1),), (Token(symbol_id=2),)
    candidates = [
        LemmaCandidate(
            theorem_id=theorem_id, conclusion_tokens=selected, premise_tokens=premises,
            usage_count=usage, is_schematic=False, namespace_id=1,
        )
        for theorem_id, premises, usage in (
            (4, (selected, other), 0), (3, (selected, other), 0),
            (2, (other, selected), 1_000_000), (1, (other, selected), 1_000_000),
        )
    ]
    ranked = rank_lemma_candidates(
        candidates, arg_tokens=(selected,), goal_tokens=selected, symbol_meta={1: atom, 2: atom},
    )
    assert [item.theorem_id for item in ranked] == [3, 4, 1, 2]
    assert ranked[0].score < ranked[-1].score


def test_step_suggestion_exposes_argument_assignments(equality_case):
    dem, proof_id, lemma_id = equality_case
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dem_services] = lambda: dem
    status, payload, _ = asyncio.run(asgi_request(
        app, "POST", f"/proofs/{proof_id}/steps/suggest",
        {"kind": "theorem", "applied_theorem_id": lemma_id, "arg_step_ords": [0, 1]},
    ))
    assert status == 200
    assert payload["arg_slots"] == [1, 0]
    assert payload["arg_candidates"] == [[1], []]
