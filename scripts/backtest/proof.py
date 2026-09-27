"""`proof_step` を Lean の項へ写す。

設計: `docs/design/ops/external-verification-backtest.md` §5

各 step は「開いた局所仮定について λ 持ち上げした 1 つの `have`」になる (§5.1)。

    have s<ord> : ∀ (v… : …), ⟦A₁⟧ → … → ⟦Aₘ⟧ → ⟦P⟧ := fun v… ha… => <core>

`have` の型は **DB に保存された `proof_step.conclusion_formula_id` からのみ**組み立てる。
翻訳器は代入も抽象も分解も計算しない —— それは Lean の β 簡約・束縛子・型合わせが行う。

依存集合 (どの仮定が開いているか) はここで数えるが、**これは信頼される計算ではない**。
数え間違えれば必要な仮説が渡らず型が合わないか、余った仮説が最終 step の型に残って
定理ステートメントと一致しない。どちらも Lean が弾く。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.backtest.dem_db import (
    BacktestError,
    DemDatabase,
    FREE_PROP_VAR,
    Step,
    Symbol,
    Theorem,
)
from scripts.backtest.formula import Node, Renderer, free_symbol_ids, parse, variable_name

GEN_BINDER = "zg"


def _union(sets: dict[int, frozenset[int]], keys: tuple[int, ...]) -> frozenset[int]:
    return frozenset().union(*(sets[key] for key in keys)) if keys else frozenset()


def binder(name: str, body: str) -> str:
    """本体で使われない束縛子には `_` を付ける。

    DEM の proof には使われない束縛が普通に現れる (本体が仮引数を無視する命題代入、
    仮定の自由変数を含むだけの ∀ 閉包、空虚な Gen など)。そのままだと Lean の
    `unusedVariables` linter が鳴り、本当に見るべき警告が埋もれる。
    """
    if re.search(rf"(?<![0-9A-Za-z_]){re.escape(name)}(?![0-9A-Za-z_])", body):
        return name
    return f"_{name}"


class Formulas:
    """`formula_id` から構文木・Lean 項・自由記号を引くキャッシュ。"""

    def __init__(self, db: DemDatabase, symbols: dict[int, Symbol], renderer: Renderer) -> None:
        self._db = db
        self._symbols = symbols
        self._renderer = renderer
        self._nodes: dict[int, Node] = {}
        self._texts: dict[int, str] = {}
        self._free: dict[int, frozenset[int]] = {}

    def node(self, formula_id: int) -> Node:
        cached = self._nodes.get(formula_id)
        if cached is None:
            cached = parse(self._db.formula_tokens(formula_id), self._symbols)
            self._nodes[formula_id] = cached
        return cached

    def text(self, formula_id: int) -> str:
        cached = self._texts.get(formula_id)
        if cached is None:
            cached = self._renderer.render(self.node(formula_id))
            self._texts[formula_id] = cached
        return cached

    def free(self, formula_id: int) -> frozenset[int]:
        cached = self._free.get(formula_id)
        if cached is None:
            cached = frozenset(free_symbol_ids(self.node(formula_id), self._symbols))
            self._free[formula_id] = cached
        return cached


@dataclass(frozen=True)
class Signature:
    """定理の Lean 側シグネチャ。パラメータはステートメントの自由記号を id 順に並べたもの。"""

    theorem_id: int
    params: tuple[int, ...]
    premise_formula_ids: tuple[int, ...]


@dataclass
class DefaultUse:
    """消えた変数に既定値を入れた箇所 (設計 §5.4)。レビューできるよう全件記録する。"""

    theorem_id: int
    step_ord: int
    symbol_id: int


@dataclass
class TranslationReport:
    theorems: int = 0
    steps: int = 0
    default_uses: list[DefaultUse] = field(default_factory=list)


class ProofTranslator:
    def __init__(
        self,
        formulas: Formulas,
        symbols: dict[int, Symbol],
        renderer: Renderer,
        signatures: dict[int, Signature],
        axiom_params: dict[int, tuple[int, ...]],
        theorem_id_for_proof: dict[int, int],
        report: TranslationReport,
    ) -> None:
        self._formulas = formulas
        self._symbols = symbols
        self._renderer = renderer
        self._signatures = signatures
        self._axiom_params = axiom_params
        self._theorem_id_for_proof = theorem_id_for_proof
        self._report = report

    # ---- 依存集合 ---------------------------------------------------------

    def _dependencies(
        self, steps: list[Step]
    ) -> tuple[dict[int, frozenset[int]], dict[int, frozenset[int]]]:
        """step ごとの (開いた仮定の formula_id, 依存する前提の ord)。

        DEM と同じく仮定は**式**でキーづける。同じ式の複数の assumption step は
        1 つのキーを共有し、1 回の ⇒導入でまとめて落ちる。formula は hash で intern
        されているので、formula_id がそのままキーになる。
        """
        assumptions: dict[int, frozenset[int]] = {}
        premises: dict[int, frozenset[int]] = {}
        by_ord = {step.ord: step for step in steps}

        for step in steps:
            if step.kind == "premise":
                if step.premise_ord is None:
                    raise BacktestError(f"premise step {step.ord} has no premise_ord")
                assumptions[step.ord] = frozenset()
                premises[step.ord] = frozenset({step.premise_ord})
                continue
            if step.kind == "assumption":
                assumptions[step.ord] = frozenset({step.conclusion_formula_id})
                premises[step.ord] = frozenset()
                continue
            if step.rule_kind == "implication_intro":
                assumption_ord, body_ord = self._two_args(step)
                discharged = by_ord[assumption_ord].conclusion_formula_id
                assumptions[step.ord] = assumptions[body_ord] - {discharged}
                premises[step.ord] = premises[body_ord]
                continue
            assumptions[step.ord] = _union(assumptions, step.arg_step_ords)
            premises[step.ord] = _union(premises, step.arg_step_ords)
        return assumptions, premises

    @staticmethod
    def _referenced_steps(steps: list[Step]) -> set[int]:
        """生成後の Lean 項が実際に名前で参照する step。

        ⇒導入の第 0 引数 (assumption step) は数えない —— λ 持ち上げでは仮定は
        `ha<formula_id>` として渡るので、assumption step 自身は参照されない。
        """
        referenced = {steps[-1].ord}
        for step in steps:
            if step.rule_kind == "implication_intro":
                referenced.add(step.arg_step_ords[1])
            else:
                referenced.update(step.arg_step_ords)
        return referenced

    @staticmethod
    def _two_args(step: Step) -> tuple[int, int]:
        if len(step.arg_step_ords) != 2:
            raise BacktestError(f"step {step.ord} ({step.rule_kind}) needs 2 args")
        return step.arg_step_ords[0], step.arg_step_ords[1]

    # ---- 翻訳 -------------------------------------------------------------

    def translate(self, theorem: Theorem, steps: list[Step]) -> str:
        if not steps:
            raise BacktestError(f"theorem {theorem.id} has a proof with no steps")

        signature = self._signatures[theorem.id]
        assumptions, premise_deps = self._dependencies(steps)
        premise_free = {
            index: self._formulas.free(formula_id)
            for index, formula_id in enumerate(theorem.premise_formula_ids)
        }
        premise_fv = {
            ord_: _union(premise_free, tuple(sorted(deps)))
            for ord_, deps in premise_deps.items()
        }

        closures: dict[int, tuple[int, ...]] = {}
        for step in steps:
            free = set(self._formulas.free(step.conclusion_formula_id))
            for formula_id in assumptions[step.ord]:
                free |= self._formulas.free(formula_id)
            closures[step.ord] = tuple(sorted(free - premise_fv[step.ord]))

        referenced = self._referenced_steps(steps)
        lines: list[str] = []
        for step in steps:
            # 参照されない step は DEM の proof に普通にある。Lean の `unusedVariables`
            # linter を鳴らさないよう `_` を付ける (参照が無いので改名しても壊れない)。
            name = f"s{step.ord}" if step.ord in referenced else f"_s{step.ord}"
            lines.append(f"  have {name} : {self._step_type(step, closures, assumptions)} :=")
            lines.append(f"    {self._step_term(theorem, step, steps, closures, assumptions)}")
        # 最終 step に仮定が残っていても、ここでは弾かない。仮説を渡さずに置けば
        # 型が `⟦A⟧ → 結論` になり、定理ステートメントと合わないことを Lean が言う。
        # 判定はカーネルの仕事であって、翻訳器の仕事ではない (設計 §1)。
        final = steps[-1]
        lines.append(
            "  "
            + self._reference(
                theorem,
                final,
                closures,
                assumptions,
                set(signature.params),
                {},
                include_hypotheses=False,
            )
        )
        self._report.theorems += 1
        self._report.steps += len(steps)
        body = "\n".join(lines)
        return "\n".join([self._header(theorem, signature, body), body])

    def _header(self, theorem: Theorem, signature: Signature, body: str) -> str:
        binders = self._renderer.binders(signature.params)
        # 前提を 1 度も使わない proof は DEM に普通にある。使わない仮説は `_h0` にして
        # linter を鳴らさない (パラメータの方は型に現れるので鳴らない)。
        premises = " ".join(
            f"({binder(f'h{index}', body)} : {self._formulas.text(formula_id)})"
            for index, formula_id in enumerate(theorem.premise_formula_ids)
        )
        parts = [part for part in (binders, premises) if part]
        prefix = (" " + " ".join(parts)) if parts else ""
        conclusion = self._formulas.text(theorem.conclusion_formula_id)
        return f"theorem dem_t{theorem.id}{prefix} : {conclusion} :="

    def _step_type(
        self,
        step: Step,
        closures: dict[int, tuple[int, ...]],
        assumptions: dict[int, frozenset[int]],
    ) -> str:
        parts: list[str] = []
        closure = closures[step.ord]
        if closure:
            parts.append(f"∀ {self._renderer.binders(closure)}, ")
        for formula_id in sorted(assumptions[step.ord]):
            parts.append(f"{self._formulas.text(formula_id)} → ")
        parts.append(self._formulas.text(step.conclusion_formula_id))
        return "".join(parts)

    def _step_term(
        self,
        theorem: Theorem,
        step: Step,
        steps: list[Step],
        closures: dict[int, tuple[int, ...]],
        assumptions: dict[int, frozenset[int]],
    ) -> str:
        signature = self._signatures[theorem.id]
        scope = set(signature.params) | set(closures[step.ord])
        core = self._core(theorem, step, steps, closures, assumptions, scope)
        names = [variable_name(symbol_id) for symbol_id in closures[step.ord]]
        names += [f"ha{formula_id}" for formula_id in sorted(assumptions[step.ord])]
        binder_names = [binder(name, core) for name in names]
        if binder_names:
            return f"fun {' '.join(binder_names)} => {core}"
        return core

    def _core(
        self,
        theorem: Theorem,
        step: Step,
        steps: list[Step],
        closures: dict[int, tuple[int, ...]],
        assumptions: dict[int, frozenset[int]],
        scope: set[int],
    ) -> str:
        by_ord = {item.ord: item for item in steps}

        def reference(referenced_ord: int, gen_map: dict[int, str]) -> str:
            return self._reference(
                theorem, by_ord[referenced_ord], closures, assumptions, scope, gen_map
            )

        if step.kind == "premise":
            return f"h{step.premise_ord}"

        if step.kind == "assumption":
            return f"ha{step.conclusion_formula_id}"

        if step.kind == "axiom":
            if step.axiom_id is None:
                raise BacktestError(f"axiom step {step.ord} has no axiom_id")
            arguments = self._instantiate(
                theorem, step, self._axiom_params[step.axiom_id], scope
            )
            return self._apply(f"dem_ax{step.axiom_id}", arguments)

        if step.kind == "theorem":
            if step.applied_proof_id is None:
                raise BacktestError(f"theorem step {step.ord} has no applied_proof_id")
            cited = self._signatures[self._theorem_id_for_proof[step.applied_proof_id]]
            arguments = self._instantiate(theorem, step, cited.params, scope)
            arguments += [reference(ord_, {}) for ord_ in step.arg_step_ords]
            return self._apply(f"dem_t{cited.theorem_id}", arguments)

        if step.rule_kind == "modus_ponens":
            antecedent_ord, implication_ord = self._two_args(step)
            return f"{reference(implication_ord, {})} {reference(antecedent_ord, {})}"

        if step.rule_kind == "generalization":
            if len(step.arg_step_ords) != 1:
                raise BacktestError(f"Gen step {step.ord} needs 1 arg")
            if step.gen_variable_symbol_id is None:
                raise BacktestError(f"Gen step {step.ord} has no gen variable")
            body = reference(step.arg_step_ords[0], {step.gen_variable_symbol_id: GEN_BINDER})
            return f"fun {binder(GEN_BINDER, body)} => {body}"

        if step.rule_kind == "implication_intro":
            assumption_ord, body_ord = self._two_args(step)
            discharged = by_ord[assumption_ord].conclusion_formula_id
            body = reference(body_ord, {})
            return f"fun {binder(f'ha{discharged}', body)} => {body}"

        raise BacktestError(f"step {step.ord}: unsupported kind {step.kind}/{step.rule_kind}")

    def _reference(
        self,
        theorem: Theorem,
        step: Step,
        closures: dict[int, tuple[int, ...]],
        assumptions: dict[int, frozenset[int]],
        scope: set[int],
        gen_map: dict[int, str],
        include_hypotheses: bool = True,
    ) -> str:
        arguments: list[str] = []
        for symbol_id in closures[step.ord]:
            replacement = gen_map.get(symbol_id)
            if replacement is not None:
                arguments.append(replacement)
            elif symbol_id in scope:
                arguments.append(variable_name(symbol_id))
            else:
                arguments.append(self._default(theorem, step, symbol_id))
        if include_hypotheses:
            arguments += [f"ha{formula_id}" for formula_id in sorted(assumptions[step.ord])]
        return self._apply(f"s{step.ord}", arguments)

    def _instantiate(
        self, theorem: Theorem, step: Step, params: tuple[int, ...], scope: set[int]
    ) -> list[str]:
        """引用先のスキーマ変数へ渡す引数列を、DB の代入から組み立てる。

        代入の**適用**はしない。適用は Lean の β 簡約が行う。
        """
        terms = dict(step.term_substs)
        props = {source: (body, formal) for source, body, formal in step.prop_substs}
        arguments: list[str] = []
        for symbol_id in params:
            if symbol_id in terms:
                arguments.append(self._formulas.text(terms[symbol_id]))
            elif symbol_id in props:
                body_formula_id, formal_params = props[symbol_id]
                body = self._formulas.text(body_formula_id)
                if formal_params:
                    binders = " ".join(
                        binder(variable_name(param), body) for param in formal_params
                    )
                    arguments.append(f"(fun {binders} => {body})")
                else:
                    arguments.append(body)
            elif symbol_id in scope:
                arguments.append(variable_name(symbol_id))
            else:
                arguments.append(self._default(theorem, step, symbol_id))
        return arguments

    def _default(self, theorem: Theorem, step: Step, symbol_id: int) -> str:
        """結論から消えた変数の既定値 (設計 §5.4)。

        値が何であれ結論は変わらない位置にしか現れないが、バックテストが持ち込んだ
        仮定なので全件を記録する。
        """
        self._report.default_uses.append(DefaultUse(theorem.id, step.ord, symbol_id))
        symbol = self._symbols[symbol_id]
        if symbol.type_name == FREE_PROP_VAR:
            if symbol.arity == 0:
                return "False"
            ignored = " ".join("_" for _ in range(symbol.arity))
            return f"(fun {ignored} => False)"
        return "u₀"

    @staticmethod
    def _apply(head: str, arguments: list[str]) -> str:
        if not arguments:
            return head
        return f"({head} {' '.join(arguments)})"
