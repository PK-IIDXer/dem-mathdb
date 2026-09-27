"""Acceptance tests for materialising a client-side plan through HTTP."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from dem.api import DemServices
from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.types import AxiomStepInput, PremiseStepInput, SymbolTypeName, Token
from webapi.deps import dem_services
from webapi.main import app


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        dem = DemServices(session)
        previous = app.dependency_overrides.copy()
        app.dependency_overrides[dem_services] = lambda: dem

        def post(path: str, body=None):
            async def request():
                messages = []
                request_body = json.dumps(body).encode() if body is not None else b""
                headers = [(b"host", b"test"), (b"content-type", b"application/json")]
                scope = {
                    "type": "http",
                    "asgi": {"version": "3.0", "spec_version": "2.4"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "root_path": "",
                    "query_string": b"",
                    "headers": headers,
                    "server": ("test", 80),
                    "client": ("test", 1234),
                }
                sent = False

                async def receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": request_body, "more_body": False}
                    await asyncio.Event().wait()

                async def send(message):
                    messages.append(message)

                await asyncio.wait_for(app(scope, receive, send), timeout=10)
                start = next(item for item in messages if item["type"] == "http.response.start")
                payload = b"".join(
                    item.get("body", b"")
                    for item in messages
                    if item["type"] == "http.response.body"
                )
                return start["status"], json.loads(payload or b"null")

            return asyncio.run(request())

        try:
            yield dem, post
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
    engine.dispose()


def _proposition(dem: DemServices, name: str):
    symbol_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
    symbol = dem.symbols.register(name, symbol_type.id, 0)
    return dem.formulas.register([Token(symbol_id=symbol.id)])


def _atom(dem: DemServices, name: str):
    symbol_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.PREDICATE.value)
    symbol = dem.symbols.register(name, symbol_type.id, 0)
    return dem.formulas.register([Token(symbol_id=symbol.id)])


def _implication(dem: DemServices, left, right):
    implication = dem.symbols.get_by_role("implication")
    return dem.formulas.register(
        [
            Token(symbol_id=implication.id),
            *dem.proofs._tokens_for_formula(left.id),
            *dem.proofs._tokens_for_formula(right.id),
        ]
    )


def _tokens(dem: DemServices, formula):
    return [
        {"symbol_id": token.symbol_id, "de_bruijn_index": token.de_bruijn_index}
        for token in dem.proofs._tokens_for_formula(formula.id)
    ]


def _backward(post, proof_id: int, *, kind: str, source_id: int, goal, subst=None):
    body = {"kind": kind, "goal_tokens": goal, "subst": subst or {}}
    body["axiom_id" if kind == "axiom" else "applied_theorem_id"] = source_id
    status, payload = post(f"/proofs/{proof_id}/steps/suggest-backward", body)
    assert status == 200
    return payload["candidates"]


def test_top_down_plan_posts_leaves_before_root_and_validates_over_http(api) -> None:
    dem, post = api
    left = _proposition(dem, "phase22a_left")
    goal = _proposition(dem, "phase22a_goal")
    implication = _implication(dem, left, goal)
    theorem = dem.theorems.register(
        "phase22a leaf to root",
        goal.id,
        [left.id, implication.id],
    )
    proof = dem.proofs.create_proof(theorem.id)

    # The client plan was chosen root-first. Materialisation is post-order:
    # both leaves must exist before the root MP is accepted.
    status, first = post(f"/proofs/{proof.id}/steps", {"kind": "premise", "premise_ord": 0})
    assert (status, first["ord"]) == (201, 0)
    status, second = post(f"/proofs/{proof.id}/steps", {"kind": "premise", "premise_ord": 1})
    assert (status, second["ord"]) == (201, 1)
    status, root = post(
        f"/proofs/{proof.id}/steps",
        {"kind": "mp", "antecedent_step_ord": 0, "implication_step_ord": 1},
    )
    assert (status, root["ord"]) == (201, 2)

    status, result = post(f"/proofs/{proof.id}/validate")
    assert status == 200
    assert result == {"status": "verified"}


def test_wrong_planned_lemma_surfaces_422_when_its_step_is_inserted(api) -> None:
    dem, post = api
    expected = _proposition(dem, "phase22a_expected")
    wrong = _proposition(dem, "phase22a_wrong")

    lemma = dem.theorems.register("phase22a wrong lemma", expected.id, [expected.id])
    lemma_proof = dem.proofs.create_proof(lemma.id)
    dem.proofs.add_step(lemma_proof.id, PremiseStepInput(0))
    dem.proofs.validate(lemma_proof.id)

    target = dem.theorems.register("phase22a wrong target", expected.id, [wrong.id])
    target_proof = dem.proofs.create_proof(target.id)
    status, leaf = post(
        f"/proofs/{target_proof.id}/steps",
        {"kind": "premise", "premise_ord": 0},
    )
    assert (status, leaf["ord"]) == (201, 0)

    status, error = post(
        f"/proofs/{target_proof.id}/steps",
        {
            "kind": "theorem",
            "applied_proof_id": lemma_proof.id,
            "arg_step_ords": [0],
            "subst": {"term_substs": [], "prop_substs": []},
        },
    )
    assert status == 422
    assert "detail" in error


@pytest.mark.parametrize("depth", [0, 1, 2, 3])
def test_backward_suggestion_matches_depths_and_materializes_every_step(api, depth) -> None:
    dem, post = api
    goal = _atom(dem, f"backward_goal_{depth}")
    antecedents = [_atom(dem, f"backward_a_{depth}_{index}") for index in range(depth)]
    conclusion = goal
    for antecedent in reversed(antecedents):
        conclusion = _implication(dem, antecedent, conclusion)
    axiom = dem.axioms.register(f"backward depth {depth}", conclusion.id)
    target = dem.theorems.register(
        f"backward target {depth}", goal.id, [item.id for item in antecedents]
    )
    proof = dem.proofs.create_proof(target.id)

    candidates = _backward(
        post, proof.id, kind="axiom", source_id=axiom.id, goal=_tokens(dem, goal)
    )
    assert [candidate["match_depth"] for candidate in candidates] == [depth]
    recipe = candidates[0]
    assert recipe["antecedent_goals"] == [_tokens(dem, item) for item in antecedents]
    assert len(recipe["intermediate_conclusions"]) == depth

    premise_ords = []
    for premise_ord in range(depth):
        status, step = post(
            f"/proofs/{proof.id}/steps", {"kind": "premise", "premise_ord": premise_ord}
        )
        assert status == 201
        premise_ords.append(step["ord"])
    status, application = post(
        f"/proofs/{proof.id}/steps",
        {"kind": "axiom", "axiom_id": axiom.id, "subst": recipe["subst"]},
    )
    assert status == 201
    implication_ord = application["ord"]
    for antecedent_ord in premise_ords:
        status, mp = post(
            f"/proofs/{proof.id}/steps",
            {
                "kind": "mp",
                "antecedent_step_ord": antecedent_ord,
                "implication_step_ord": implication_ord,
            },
        )
        assert status == 201
        implication_ord = mp["ord"]
    status, result = post(f"/proofs/{proof.id}/validate")
    assert (status, result) == (200, {"status": "verified"})


def test_backward_suggestion_does_not_search_at_depth_four(api) -> None:
    dem, post = api
    goal = _atom(dem, "backward_depth_four_goal")
    conclusion = goal
    for index in reversed(range(4)):
        conclusion = _implication(dem, _atom(dem, f"backward_depth_four_{index}"), conclusion)
    axiom = dem.axioms.register("backward depth four", conclusion.id)
    target = dem.theorems.register("backward depth four target", goal.id)
    proof = dem.proofs.create_proof(target.id)

    assert _backward(
        post, proof.id, kind="axiom", source_id=axiom.id, goal=_tokens(dem, goal)
    ) == []


def test_backward_suggestion_recomputes_identity_default_from_substitution_override(api) -> None:
    dem, post = api
    schema = _proposition(dem, "backward_override_schema")
    replacement = _atom(dem, "backward_override_replacement")
    goal = _atom(dem, "backward_override_goal")
    axiom = dem.axioms.register(
        "backward override axiom", _implication(dem, schema, goal).id
    )
    target = dem.theorems.register("backward override target", goal.id)
    proof = dem.proofs.create_proof(target.id)

    initial = _backward(
        post, proof.id, kind="axiom", source_id=axiom.id, goal=_tokens(dem, goal)
    )[0]
    schema_id = dem.proofs._tokens_for_formula(schema.id)[0].symbol_id
    assert initial["defaulted_to_identity"] == [schema_id]
    assert initial["antecedent_goals"] == [_tokens(dem, schema)]

    overridden = _backward(
        post,
        proof.id,
        kind="axiom",
        source_id=axiom.id,
        goal=_tokens(dem, goal),
        subst={
            "prop_substs": [
                {
                    "source_symbol_id": schema_id,
                    "body_formula_id": replacement.id,
                    "formal_param_symbol_ids": [],
                }
            ],
            "term_substs": [],
        },
    )[0]
    assert overridden["defaulted_to_identity"] == []
    assert overridden["antecedent_goals"] == [_tokens(dem, replacement)]


def test_backward_suggestion_materializes_miller_pattern_from_the_consequent(api) -> None:
    dem, post = api
    term_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    prop_type = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    x = dem.symbols.register("backward_miller_x", term_type.id, 0)
    dem.symbols.register("backward_miller_y", term_type.id, 0)
    phi = dem.symbols.register("backward_miller_phi", prop_type.id, 1)
    universal = dem.symbols.get_by_role("universal_quantifier")
    equality = dem.symbols.get_by_role("equality")
    antecedent = _atom(dem, "backward_miller_antecedent")
    consequent = dem.formulas.register(
        [
            Token(symbol_id=universal.id),
            Token(symbol_id=phi.id),
            Token(de_bruijn_index=0),
        ]
    )
    goal = dem.formulas.register(
        [
            Token(symbol_id=universal.id),
            Token(symbol_id=equality.id),
            Token(de_bruijn_index=0),
            Token(symbol_id=x.id),
        ]
    )
    axiom = dem.axioms.register(
        "backward miller axiom", _implication(dem, antecedent, consequent).id
    )
    target = dem.theorems.register("backward miller target", goal.id)
    proof = dem.proofs.create_proof(target.id)

    recipe = _backward(
        post, proof.id, kind="axiom", source_id=axiom.id, goal=_tokens(dem, goal)
    )[0]
    assert recipe["match_depth"] == 1
    assert recipe["undetermined"] == []
    assert recipe["antecedent_goals"] == [_tokens(dem, antecedent)]
    assert len(recipe["subst"]["prop_substs"]) == 1
    assert len(recipe["subst"]["prop_substs"][0]["formal_param_symbol_ids"]) == 1


def test_double_negation_body_is_completed_by_nested_backward_recipes_and_discharge(api) -> None:
    dem, post = api
    phi = _atom(dem, "backward_double_negation_phi")
    bottom = _atom(dem, "backward_double_negation_bottom")
    not_phi = _implication(dem, phi, bottom)
    not_not_phi = _implication(dem, not_phi, bottom)
    goal = _implication(dem, phi, not_not_phi)
    derive_not_phi = dem.axioms.register(
        "backward derive not phi", _implication(dem, phi, not_phi).id
    )
    introduce_double_negation = dem.axioms.register(
        "backward introduce double negation",
        _implication(dem, not_phi, not_not_phi).id,
    )
    theorem = dem.theorems.register("backward double negation target", goal.id)
    proof = dem.proofs.create_proof(theorem.id)

    status, assumption = post(
        f"/proofs/{proof.id}/steps",
        {"kind": "assumption", "conclusion_formula_id": phi.id},
    )
    assert status == 201
    outer = _backward(
        post,
        proof.id,
        kind="axiom",
        source_id=introduce_double_negation.id,
        goal=_tokens(dem, not_not_phi),
    )[0]
    assert outer["antecedent_goals"] == [_tokens(dem, not_phi)]
    inner = _backward(
        post,
        proof.id,
        kind="axiom",
        source_id=derive_not_phi.id,
        goal=outer["antecedent_goals"][0],
    )[0]
    assert inner["antecedent_goals"] == [_tokens(dem, phi)]

    status, inner_axiom = post(
        f"/proofs/{proof.id}/steps",
        {"kind": "axiom", "axiom_id": derive_not_phi.id, "subst": inner["subst"]},
    )
    assert status == 201
    status, not_phi_step = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "mp",
            "antecedent_step_ord": assumption["ord"],
            "implication_step_ord": inner_axiom["ord"],
        },
    )
    assert status == 201
    status, outer_axiom = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "axiom",
            "axiom_id": introduce_double_negation.id,
            "subst": outer["subst"],
        },
    )
    assert status == 201
    status, body = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "mp",
            "antecedent_step_ord": not_phi_step["ord"],
            "implication_step_ord": outer_axiom["ord"],
        },
    )
    assert status == 201
    status, _ = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "imp_intro",
            "assumption_step_ord": assumption["ord"],
            "body_step_ord": body["ord"],
        },
    )
    assert status == 201
    status, result = post(f"/proofs/{proof.id}/validate")
    assert (status, result) == (200, {"status": "verified"})


@pytest.mark.parametrize("with_premise", [False, True])
def test_backward_theorem_suggestion_materializes_to_verified(api, with_premise) -> None:
    dem, post = api
    premise = _atom(dem, f"backward_theorem_premise_{with_premise}")
    antecedent = _atom(dem, f"backward_theorem_antecedent_{with_premise}")
    goal = _atom(dem, f"backward_theorem_goal_{with_premise}")
    implication = _implication(dem, antecedent, goal)
    source_axiom = dem.axioms.register(
        f"backward theorem source axiom {with_premise}", implication.id
    )
    source_theorem = dem.theorems.register(
        f"backward theorem source {with_premise}",
        implication.id,
        [premise.id] if with_premise else [],
    )
    source_proof = dem.proofs.create_proof(source_theorem.id)
    if with_premise:
        dem.proofs.add_step(source_proof.id, PremiseStepInput(0))
    dem.proofs.add_step(source_proof.id, AxiomStepInput(source_axiom.id))
    dem.proofs.validate(source_proof.id)

    target_premises = [premise, antecedent] if with_premise else [antecedent]
    target = dem.theorems.register(
        f"backward theorem target {with_premise}",
        goal.id,
        [item.id for item in target_premises],
    )
    proof = dem.proofs.create_proof(target.id)
    recipe = _backward(
        post,
        proof.id,
        kind="theorem",
        source_id=source_theorem.id,
        goal=_tokens(dem, goal),
    )[0]
    assert recipe["match_depth"] == 1
    assert recipe["premise_count"] == (1 if with_premise else 0)
    assert recipe["premise_goals"] == ([_tokens(dem, premise)] if with_premise else [])

    inserted = []
    for premise_ord in range(len(target_premises)):
        status, step = post(
            f"/proofs/{proof.id}/steps", {"kind": "premise", "premise_ord": premise_ord}
        )
        assert status == 201
        inserted.append(step["ord"])
    theorem_args = inserted[:1] if with_premise else []
    status, theorem_step = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "theorem",
            "applied_proof_id": recipe["applied_proof_id"],
            "arg_step_ords": theorem_args,
            "subst": recipe["subst"],
        },
    )
    assert status == 201
    status, _ = post(
        f"/proofs/{proof.id}/steps",
        {
            "kind": "mp",
            "antecedent_step_ord": inserted[-1],
            "implication_step_ord": theorem_step["ord"],
        },
    )
    assert status == 201
    status, result = post(f"/proofs/{proof.id}/validate")
    assert (status, result) == (200, {"status": "verified"})
