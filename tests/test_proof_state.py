from __future__ import annotations

from statistics import median
from time import perf_counter

import pytest
from sqlalchemy import event, func, select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import Base
from dem.db.models.theorem import Proof, ProofStep
from dem.db.seed import seed_inference_rules, seed_language
from dem.errors import ProofValidationError
from dem.types import (
    AssumptionStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    SymbolTypeName,
    Token,
)


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        seed_inference_rules(session)
        yield DemServices(session)
    engine.dispose()


def _proposition(dem: DemServices, name: str = "phase2_phi"):
    symbol_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
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


def test_state_of_a_fresh_draft_is_the_theorem_goal(dem) -> None:
    proposition = _proposition(dem)
    theorem = dem.theorems.register(
        "phase2 fresh draft state",
        proposition.id,
        [proposition.id],
    )
    proof = dem.proofs.create_proof(theorem.id)

    state = dem.proofs.get_state(proof.id)

    assert state.goal_tokens == [
        Token(symbol_id=dem.symbols.get_by_name("phase2_phi").id)
    ]
    assert [(item.ord, item.tokens, item.used_by) for item in state.premises] == [
        (0, state.goal_tokens, [])
    ]
    assert state.established == []
    assert state.open_assumptions == []
    assert state.reached_goal is False
    assert state.blocking == ["goal_not_reached"]


def test_established_matches_the_steps_accepted_by_validation(dem) -> None:
    proposition = _proposition(dem)
    theorem = dem.theorems.register(
        "phase2 established state",
        proposition.id,
        [proposition.id],
    )
    proof = dem.proofs.create_proof(theorem.id)
    step = dem.proofs.add_step(proof.id, PremiseStepInput(0))

    state = dem.proofs.get_state(proof.id)

    assert len(state.established) == 1
    established = state.established[0]
    assert established.ord == step.ord
    assert established.tokens == dem.proofs._tokens_for_formula(step.conclusion_formula_id)
    assert established.step_kind == "premise"
    assert established.depends_on_premises == [0]
    assert established.depends_on_assumptions == []
    assert state.premises[0].used_by == [0]
    assert state.reached_goal is True
    assert state.blocking == []

    dem.proofs.validate(proof.id)
    assert proof.status == "verified"

def test_open_assumption_is_keyed_by_tokens(dem) -> None:
    proposition = _proposition(dem)
    goal = _implication(dem, proposition, proposition)
    theorem = dem.theorems.register("phase2 duplicate assumptions", goal.id)
    proof = dem.proofs.create_proof(theorem.id)
    dem.proofs.add_step(proof.id, AssumptionStepInput(), proposition.id)
    dem.proofs.add_step(proof.id, AssumptionStepInput(), proposition.id)

    open_state = dem.proofs.get_state(proof.id)
    assert [item.step_ord for item in open_state.open_assumptions] == [0, 1]

    dem.proofs.add_step(proof.id, ImplicationIntroStepInput(0, 1))
    closed_state = dem.proofs.get_state(proof.id)
    assert closed_state.open_assumptions == []
    assert closed_state.reached_goal is True
    assert closed_state.blocking == []


def test_rejected_proof_reports_validation_failure_without_replay(dem) -> None:
    assumed = _proposition(dem)
    goal = _proposition(dem, "phase2_psi")
    theorem = dem.theorems.register("phase2 rejected state", goal.id)
    proof = dem.proofs.create_proof(theorem.id)
    dem.proofs.add_step(proof.id, AssumptionStepInput(), assumed.id)

    with pytest.raises(ProofValidationError) as caught:
        dem.proofs.validate(proof.id)
    assert caught.value.code == "proof.final_mismatch"
    assert proof.status == "rejected"

    statements: list[str] = []

    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(dem.session.bind, "before_cursor_execute", record_statement)
    try:
        state = dem.proofs.get_state(proof.id)
    finally:
        event.remove(dem.session.bind, "before_cursor_execute", record_statement)

    assert state.goal_tokens == dem.proofs._tokens_for_formula(goal.id)
    assert state.premises == []
    assert state.established == []
    assert state.open_assumptions == []
    assert state.reached_goal is False
    assert state.blocking == ["validation_failed"]
    assert not any(" from proof_step" in statement for statement in statements)


def test_mp_followups_chain_to_the_goal_and_remain_kernel_checked(dem) -> None:
    a = _proposition(dem)
    symbol_type = dem.symbols.get_symbol_type_by_name(
        SymbolTypeName.FREE_PROP_VAR.value
    )
    b_symbol = dem.symbols.register("phase2_psi", symbol_type.id, 0)
    c_symbol = dem.symbols.register("phase2_chi", symbol_type.id, 0)
    b = dem.formulas.register([Token(symbol_id=b_symbol.id)])
    c = dem.formulas.register([Token(symbol_id=c_symbol.id)])
    b_to_c = _implication(dem, b, c)
    a_to_b_to_c = _implication(dem, a, b_to_c)
    theorem = dem.theorems.register(
        "phase2 MP followup chain",
        c.id,
        [a.id, b.id, a_to_b_to_c.id],
    )
    proof = dem.proofs.create_proof(theorem.id)
    dem.proofs.add_step(proof.id, PremiseStepInput(0))
    dem.proofs.add_step(proof.id, PremiseStepInput(1))
    dem.proofs.add_step(proof.id, PremiseStepInput(2))

    proposals = dem.proofs.list_step_followups(proof.id, 2)
    assert [
        (
            item.antecedent_step_ord,
            item.implication_step_ord,
            item.conclusion_tokens,
            item.reaches_goal,
        )
        for item in proposals
    ] == [
        (0, 2, dem.proofs._tokens_for_formula(b_to_c.id), False),
        (1, 3, dem.proofs._tokens_for_formula(c.id), True),
    ]

    first = dem.proofs.add_step(proof.id, MPStepInput(0, 2))
    second = dem.proofs.add_step(proof.id, MPStepInput(1, first.ord))
    assert second.ord == 4
    dem.proofs.validate(proof.id)
    assert proof.status == "verified"
