"""`dedupe_persisted_steps` の不変条件。

設計は docs/design/todo/proof-step-inflation.md §4 D。実データに対する効果は
seed のテストが step 数の pin で見ているので、ここでは規則そのものを見る。
"""

from __future__ import annotations

from dem.db.seeds._dedupe import dedupe_persisted_steps
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    GenStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    TheoremStepInput,
)


def test_identical_closed_derivations_are_shared() -> None:
    steps = [
        (AxiomStepInput(1), 10),
        (PremiseStepInput(0), 20),
        (MPStepInput(1, 0), 30),
        (AxiomStepInput(1), 10),
        (MPStepInput(2, 3), 40),
    ]
    result = dedupe_persisted_steps(steps)

    assert len(result) == 4
    assert result[-1][1] == 40
    # 2 本目の公理インスタンスが消え、最後の MP が 1 本目を指している。
    assert result[-1][0] == MPStepInput(2, 0)


def test_same_conclusion_with_different_premise_deps_is_not_shared() -> None:
    """Gen の側条件は premise 依存まで見るので、依存が違えば併合しない。"""
    steps = [
        (PremiseStepInput(0), 10),
        (PremiseStepInput(1), 10),
        (AxiomStepInput(1), 20),
        (MPStepInput(0, 2), 30),
        (MPStepInput(1, 2), 30),
        (MPStepInput(3, 4), 40),
    ]
    result = dedupe_persisted_steps(steps)

    assert len(result) == 6
    assert result[-1][0] == MPStepInput(3, 4)


def test_assumption_dependent_steps_are_never_shared() -> None:
    steps = [
        (AssumptionStepInput(), 10),
        (AxiomStepInput(1), 20),
        (MPStepInput(0, 1), 30),
        (MPStepInput(0, 1), 30),
        (ImplicationIntroStepInput(0, 3), 40),
    ]
    result = dedupe_persisted_steps(steps)

    # 仮定に依存する 2 本の MP は残る。落ちるのは到達不能な ord 2 だけ。
    assert [formula for _, formula in result] == [10, 20, 30, 40]
    assert result[-1][0] == ImplicationIntroStepInput(0, 2)


def test_discharged_conclusion_is_shareable_again() -> None:
    """⇒導入で仮定が落ちた後の結論は、依存が空なので共有できる。"""
    steps = [
        (AssumptionStepInput(), 10),
        (ImplicationIntroStepInput(0, 0), 20),
        (AssumptionStepInput(), 10),
        (ImplicationIntroStepInput(2, 2), 20),
        (AxiomStepInput(1), 30),
        (MPStepInput(1, 4), 40),
        (MPStepInput(3, 4), 40),
        (MPStepInput(5, 6), 50),
    ]
    result = dedupe_persisted_steps(steps)

    assert result[-1][1] == 50
    # 同じ ⇒導入の結論を二度作っていた分が 1 本に畳まれている。
    assert sum(1 for _, formula in result if formula == 20) == 1


def test_unreachable_steps_are_dropped() -> None:
    steps = [
        (AxiomStepInput(1), 10),
        (AxiomStepInput(2), 20),
        (PremiseStepInput(0), 30),
        (MPStepInput(2, 0), 40),
    ]
    result = dedupe_persisted_steps(steps)

    assert [formula for _, formula in result] == [10, 30, 40]


def test_is_idempotent() -> None:
    steps = [
        (PremiseStepInput(0), 10),
        (AxiomStepInput(1), 20),
        (MPStepInput(0, 1), 30),
        (AxiomStepInput(1), 20),
        (MPStepInput(0, 3), 30),
        (GenStepInput(4, 7), 40),
        (TheoremStepInput(9, None, arg_step_ords=(2, 5)), 50),
    ]
    once = dedupe_persisted_steps(steps)
    twice = dedupe_persisted_steps(once)

    assert once == twice
    assert once[-1][1] == 50


def test_empty_input() -> None:
    assert dedupe_persisted_steps([]) == []
