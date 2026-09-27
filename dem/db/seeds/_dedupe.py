"""永続化の直前に、同じ判断を二度導いている step を畳む。

大きな proof では、同じ結論を同じ依存の下で二度導く重複が実際に生じる。

generator を直すのではなくここで畳むのは、重複が helper をまたいで生じる
からである。helper ごとにキャッシュを置くと、同じ結論を別経路で出している分を
取り逃がし、helper ごとにスコープの正しさを考えることになる。

**畳んでよい条件は「結論式が同じ」だけでは足りない。** Gen の側条件は
`premise_deps` を走査して「変数が開いた依存の中に自由に現れない」ことを見ており、
前提依存まで対象にしている (`dem/services/proof.py` の `generalization` 分岐)。
同じ結論式でも依存集合が違う step を差し替えると、後続の Gen が壊れうる。
そこで:

    結論式が同じ かつ 依存集合が同じ かつ 依存集合に assumption を含まない

のときだけ共有する。判断が同一になるので、後続のどの検査 (Gen の側条件、
⇒導入の discharge、最終行に未 discharge の仮定が残っていないか) も挙動が
変わらない。`assumption` を除くのは、discharge 済みの地点で仮定依存の step を
再利用すると依存が最終行へ漏れるためである。

依存集合の作り方はカーネル (`dem/services/proof.py` の `DepKey`) をそのまま
写している。前提は序数で、仮定は論理式でキーされる。ここでは論理式を id で
持つが、formula は intern されているので同じことである。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from dem.types import (
    AssumptionStepInput,
    ImplicationIntroStepInput,
    PremiseStepInput,
    ProofStepInput,
    rebase_step_input,
)

DepKey: TypeAlias = tuple[str, int]

_PREMISE = "premise"
_ASSUMPTION = "assumption"

PersistedStep: TypeAlias = tuple[ProofStepInput, int]


def _referenced(step_input: ProofStepInput) -> tuple[int, ...]:
    """`step_input` が前の step を指している序数。`rebase_step_input` と対。"""
    referenced: list[int] = []

    def collect(ord_: int) -> int:
        referenced.append(ord_)
        return ord_

    rebase_step_input(step_input, collect)
    return tuple(referenced)


def dedupe_persisted_steps(steps: Sequence[PersistedStep]) -> list[PersistedStep]:
    """`(step_input, formula_id)` の列から、重複した導出を落とす。

    冪等である —— 一度畳んだ列をもう一度渡しても変わらない。最終行の結論式も
    変わらない (最終行を指す参照だけを残すので、到達不能になった step が消える)。
    """
    if not steps:
        return []

    deps: list[frozenset[DepKey]] = []
    for step_input, formula_id in steps:
        if isinstance(step_input, PremiseStepInput):
            deps.append(frozenset({(_PREMISE, step_input.premise_ord)}))
            continue
        if isinstance(step_input, AssumptionStepInput):
            deps.append(frozenset({(_ASSUMPTION, formula_id)}))
            continue
        current: set[DepKey] = set()
        for ord_ in _referenced(step_input):
            current |= deps[ord_]
        if isinstance(step_input, ImplicationIntroStepInput):
            discharged = steps[step_input.assumption_step_ord][1]
            current -= {(_ASSUMPTION, discharged)}
        deps.append(frozenset(current))

    canonical: list[int] = []
    first: dict[tuple[int, frozenset[DepKey]], int] = {}
    for index, (_, formula_id) in enumerate(steps):
        if any(kind == _ASSUMPTION for kind, _ in deps[index]):
            canonical.append(index)
            continue
        key = (formula_id, deps[index])
        existing = first.get(key)
        if existing is None:
            first[key] = index
            canonical.append(index)
        else:
            canonical.append(existing)

    # 参照は必ず後ろ向きなので、最終行の祖先だけを残せば序数の順序は保たれる。
    final = canonical[len(steps) - 1]
    keep: set[int] = set()
    stack = [final]
    while stack:
        index = stack.pop()
        if index in keep:
            continue
        keep.add(index)
        for ord_ in _referenced(steps[index][0]):
            stack.append(canonical[ord_])

    order = sorted(keep)
    renumbered = {index: position for position, index in enumerate(order)}
    result: list[PersistedStep] = []
    for index in order:
        step_input, formula_id = steps[index]
        result.append(
            (
                rebase_step_input(
                    step_input, lambda ord_: renumbered[canonical[ord_]]
                ),
                formula_id,
            )
        )
    return result
