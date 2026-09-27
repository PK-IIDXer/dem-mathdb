from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.language import Formula, Symbol
from dem.db.models.theorem import Proof, Theorem, TheoremPremise
from dem.db.seed_labels import (
    seed_proof_name,
    theorem_conclusion_formula_remark,
    theorem_premise_formula_remark,
)
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService, abstract_and_quantify_pure, decompose_implication_pure
from dem.db.seeds._variable_pool import SeedSymbolService as SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    GenStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    ProofStepInput,
    PropSubst,
    Substitution,
    TheoremStepInput,
    Token,
)


@dataclass(frozen=True)
class ProofStepSpec:
    input: ProofStepInput
    conclusion_tokens: list[Token] | int


@dataclass(frozen=True)
class DischargeStep:
    """One line of a derivation, in a form self-describing enough to run both
    `HilbertToolkit.discharge` and its elimination procedure
    `HilbertToolkit.expand_implication_intro`.

    - "premise": one of the theorem's own premises (`premise_index`).
    - "assumption": a local assumption, discharged by a later "imp_intro".
      Unlike a premise it is not tied to the theorem's premise list, so a
      derivation can open and close one without the theorem declaring it.
    - "fact": a premise-independent step (an axiom/theorem citation);
      `fact_input` is what to re-cite it with.
    - "mp": modus ponens combining two prior lines (`mp_left` = antecedent's
      original index, `mp_right` = implication's original index).
    - "gen": generalization over a prior line (`gen_body_ord` = the
      generalized step's original index, `gen_variable_symbol_id` = the
      variable generalized over).
    - "imp_intro": ⇒introduction, closing the assumption at
      `imp_assumption_ord` over the line at `imp_body_ord`.
    - "applied": a *premised* theorem cited with arguments (`fact_input` is the
      `TheoremStepInput`, `applied_arg_ords` are the original indices of the
      lines feeding its premises).  Unlike a "fact" its conclusion depends on
      earlier lines, so `_ks_lift` cannot K-lift it; it goes through the cited
      theorem's curried form instead (design doc 9.11 (B)).
    """

    kind: str
    tokens: list[Token]
    fact_input: ProofStepInput | None = None
    premise_index: int | None = None
    mp_left: int | None = None
    mp_right: int | None = None
    gen_body_ord: int | None = None
    gen_variable_symbol_id: int | None = None
    imp_assumption_ord: int | None = None
    imp_body_ord: int | None = None
    applied_arg_ords: tuple[int, ...] = ()


_BACK_REFERENCE_FIELDS = (
    "mp_left",
    "mp_right",
    "gen_body_ord",
    "imp_assumption_ord",
    "imp_body_ord",
)

#: Tuple-valued back references, renumbered the same way as the scalar ones.
_BACK_REFERENCE_TUPLE_FIELDS = ("applied_arg_ords",)


def remap_discharge_ordinals(
    step: DischargeStep, remap: Callable[[int], int]
) -> DischargeStep:
    """Put every back-reference in `step` through `remap`.

    The `DischargeStep` counterpart of `dem.types.rebase_step_input`: use it
    whenever a derivation is spliced into another one, so a step kind added
    later cannot leave a caller silently copying a stale ordinal.

    `premise_index` is left alone -- it indexes the theorem's premise list, not
    the step list.
    """
    changed = {
        field: remap(getattr(step, field))
        for field in _BACK_REFERENCE_FIELDS
        if getattr(step, field) is not None
    }
    changed.update(
        {
            field: tuple(remap(ord_) for ord_ in getattr(step, field))
            for field in _BACK_REFERENCE_TUPLE_FIELDS
            if getattr(step, field)
        }
    )
    return replace(step, **changed) if changed else step


def shift_discharge_ordinals(step: DischargeStep, offset: int) -> DischargeStep:
    """`remap_discharge_ordinals` for the common case of a constant shift."""
    if offset == 0:
        return step
    return remap_discharge_ordinals(step, lambda ord_: ord_ + offset)


class HilbertToolkit:
    """Eliminate admissible implication-introduction steps into K/S proofs.

    The toolkit registers no bundled theorem. Every expansion is assembled
    directly from instances of the A-only Hilbert axioms plus MP and Gen.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.symbols = SymbolService(session)
        self.formulas = FormulaService(session)
        self.axioms = AxiomService(session)
        self.theorems = TheoremService(session)
        self.proofs = ProofService(session, authoring_via="seed")

        self.imp_ = self.symbols.get_by_role("implication")
        self.forall_ = self.symbols.get_by_role("universal_quantifier")
        self.phi = self.symbols.get_by_name("φ")
        self.psi = self.symbols.get_by_name("ψ")
        self.chi = self.symbols.get_by_name("χ")
        self.phi1 = self.symbols.get_by_name("φ¹")
        self.psi1 = self.symbols.get_by_name("ψ¹")

    # -- token helpers --------------------------------------------------------

    def atom(self, symbol: Symbol) -> list[Token]:
        return [Token(symbol_id=symbol.id)]

    def imp(self, left: list[Token], right: list[Token]) -> list[Token]:
        return [Token(symbol_id=self.imp_.id), *left, *right]

    # -- Deduction Theorem: ⇒introduction, and its elimination procedure ------
    #
    # `discharge` turns a derivation of L_n from premises [..., discharged, ...]
    # into a derivation of `discharged -> L_n` with `discharged` removed from
    # the premise list. Applying it twice to a 2-premise derivation yields a
    # fully premise-free ("pure") implication.
    #
    # Since §9 that is one kernel step: the cited premise becomes an
    # "assumption" line and a single "imp_intro" closes it. The K/S rewriting
    # that used to do the same job by hand survives verbatim below as
    # `expand_implication_intro`/`_ks_lift` -- see the invariant (E) tests in
    # tests/test_soundness_invariants.py.

    def discharge(
        self,
        original: list[DischargeStep],
        target_premise_index: int,
        discharged_tokens: list[Token],
    ) -> list[DischargeStep]:
        """Close `target_premise_index` into an implication, in one step.

        The output keeps the input's ordinals line-for-line (the cited premise
        becomes an assumption in place), appends the ⇒intro, and renumbers the
        surviving premises so the discharged one leaves no hole -- the same
        contract the K/S implementation had, so callers are unaffected.
        """
        cited = any(
            step.kind == "premise" and step.premise_index == target_premise_index
            for step in original
        )
        new_steps: list[DischargeStep] = []
        assumption_ord: int | None = None
        if not cited:
            # The premise is never cited. Vacuous discharge is sound -- it is
            # exactly what `hilbert_k` says -- so open the assumption up front,
            # only to have something for the ⇒intro to close. Opening it first
            # (rather than last) keeps the final line the derivation's own.
            assumption_ord = 0
            new_steps.append(DischargeStep(kind="assumption", tokens=discharged_tokens))
        offset = len(new_steps)

        for step in original:
            if step.kind == "premise" and step.premise_index == target_premise_index:
                if step.tokens != discharged_tokens:
                    raise ValidationError(
                        "discharge: discharged_tokens do not match the cited premise"
                    )
                assumption_ord = len(new_steps)
                new_steps.append(DischargeStep(kind="assumption", tokens=discharged_tokens))
            elif step.kind == "premise":
                assert step.premise_index is not None
                new_steps.append(
                    replace(
                        step,
                        premise_index=step.premise_index
                        - (1 if step.premise_index > target_premise_index else 0),
                    )
                )
            else:
                new_steps.append(shift_discharge_ordinals(step, offset))

        assert assumption_ord is not None
        body_ord = len(new_steps) - 1
        new_steps.append(
            DischargeStep(
                kind="imp_intro",
                tokens=self.imp(discharged_tokens, new_steps[body_ord].tokens),
                imp_assumption_ord=assumption_ord,
                imp_body_ord=body_ord,
            )
        )
        return new_steps

    def expand_implication_intro(self, steps: list[DischargeStep]) -> list[DischargeStep]:
        """Rewrite every "imp_intro" away, leaving premise/fact/mp/gen only.

        This is the elimination procedure that keeps ⇒introduction from
        widening the trust boundary (design doc §9.4): it is a constructive
        proof of the Deduction Theorem, so a derivation using ⇒intro proves
        nothing that MP and Gen alone could not. Invariant (E) -- expand, then
        re-check with the kernel -- is pinned in
        tests/test_soundness_invariants.py.

        Nested ⇒intros are expanded innermost-first, so each expansion sees a
        prefix that is already free of them.
        """
        current = list(steps)
        while True:
            index = next(
                (i for i, step in enumerate(current) if step.kind == "imp_intro"), None
            )
            if index is None:
                return current
            current = self._expand_one_implication_intro(current, index)

    def ks_discharge(
        self,
        original: list[DischargeStep],
        target_premise_index: int,
        discharged_tokens: list[Token],
    ) -> list[DischargeStep]:
        """`discharge`, then immediately eliminate the ⇒intro it produced.

        The Hilbert expansion is constructed directly from K, S and MP, keeping
        the elimination procedure independent of any pre-seeded derived theorem.
        """
        return self.expand_implication_intro(
            self.discharge(original, target_premise_index, discharged_tokens)
        )

    def _expand_one_implication_intro(
        self, steps: list[DischargeStep], index: int
    ) -> list[DischargeStep]:
        step = steps[index]
        assert step.imp_assumption_ord is not None and step.imp_body_ord is not None
        assumption_ord = step.imp_assumption_ord
        body_ord = step.imp_body_ord
        if body_ord != index - 1:
            # `discharge` always appends the ⇒intro directly onto the line it
            # closes; without that the lifted body would not end up last and
            # the derivation's conclusion would move.
            raise NotImplementedError(
                "expand_implication_intro: ⇒intro must directly follow its body"
            )
        discharged_tokens = steps[assumption_ord].tokens

        new_prefix, lifted, assumption_map, surviving = self._ks_lift(
            steps[:index],
            discharged_tokens,
            discharged_assumption_ord=assumption_ord,
            required_ord=body_ord,
        )
        if new_prefix[lifted[body_ord]].tokens != step.tokens:
            raise ValidationError("expand_implication_intro: lifted body does not match")

        tail_map: dict[int, int] = {}

        def remap(ord_: int) -> int:
            if ord_ < index:
                try:
                    return surviving[ord_]
                except KeyError as exc:
                    raise ValidationError(
                        "expand_implication_intro: tail references a line that "
                        "still depends on the discharged assumption"
                    ) from exc
            if ord_ == index:
                return lifted[body_ord]
            try:
                return tail_map[ord_]
            except KeyError as exc:
                raise ValidationError(
                    "expand_implication_intro: tail references an unavailable line"
                ) from exc

        result = list(new_prefix)
        for tail_ord, tail_step in enumerate(steps[index + 1 :], start=index + 1):
            if tail_step.kind == "mp":
                assert tail_step.mp_left is not None and tail_step.mp_right is not None
                result.append(
                    replace(
                        tail_step,
                        mp_left=remap(tail_step.mp_left),
                        mp_right=remap(tail_step.mp_right),
                    )
                )
                tail_map[tail_ord] = len(result) - 1
            elif tail_step.kind == "gen":
                assert tail_step.gen_body_ord is not None
                result.append(replace(tail_step, gen_body_ord=remap(tail_step.gen_body_ord)))
                tail_map[tail_ord] = len(result) - 1
            elif tail_step.kind == "applied":
                result.append(
                    replace(
                        tail_step,
                        applied_arg_ords=tuple(
                            remap(ord_) for ord_ in tail_step.applied_arg_ords
                        ),
                    )
                )
                tail_map[tail_ord] = len(result) - 1
            elif tail_step.kind == "imp_intro":
                assert (
                    tail_step.imp_assumption_ord is not None
                    and tail_step.imp_body_ord is not None
                )
                try:
                    new_assumption_ord = (
                        assumption_map[tail_step.imp_assumption_ord]
                        if tail_step.imp_assumption_ord < index
                        else remap(tail_step.imp_assumption_ord)
                    )
                except KeyError as exc:
                    # The kernel keys local assumptions by formula.  An inner
                    # ⇒intro over A therefore discharges every equal A, making
                    # an enclosing ⇒intro over A vacuous.  Eliminate that
                    # admissible step with K: B, B→(A→B) ⊢ A→B.
                    if steps[tail_step.imp_assumption_ord].tokens != discharged_tokens:
                        raise NotImplementedError(
                            "expand_implication_intro: nested ⇒intro assumption was lost"
                        ) from exc
                    body_new_ord = remap(tail_step.imp_body_ord)
                    body_tokens = result[body_new_ord].tokens
                    k_axiom = self.axioms.get_by_name("hilbert_k")
                    sigma_k = Substitution(
                        prop_substs=(
                            PropSubst(self.phi.id, self._formula(body_tokens).id),
                            PropSubst(self.psi.id, self._formula(discharged_tokens).id),
                        )
                    )
                    k_tokens = self.proofs.compute_substituted_tokens(
                        k_axiom.formula_id, sigma_k
                    )
                    k_ord = len(result)
                    result.append(
                        DischargeStep(
                            kind="fact",
                            tokens=k_tokens,
                            fact_input=AxiomStepInput(k_axiom.id, sigma_k),
                        )
                    )
                    result.append(
                        DischargeStep(
                            kind="mp",
                            tokens=tail_step.tokens,
                            mp_left=body_new_ord,
                            mp_right=k_ord,
                        )
                    )
                    tail_map[tail_ord] = len(result) - 1
                    continue
                result.append(
                    replace(
                        tail_step,
                        imp_assumption_ord=new_assumption_ord,
                        imp_body_ord=remap(tail_step.imp_body_ord),
                    )
                )
                tail_map[tail_ord] = len(result) - 1
            else:
                result.append(tail_step)
                tail_map[tail_ord] = len(result) - 1
        return result

    # -- the K/S/self_imp construction of the Deduction Theorem ---------------

    def curried_form(self, applied_proof_id: int) -> tuple[Proof, list[list[Token]], list[Token]]:
        """A premised theorem's curried twin ``|- p1 -> ... -> pn -> C``.

        Built on demand from the *stored* proof: `ProofService.reconstruct_steps`
        replays it as step specs and each premise is discharged from the last
        inwards.  This is what makes §5 rule 12 unnecessary -- a caller no longer
        has to publish a 0-premise form in advance, because the toolkit can
        derive one for any verified proof it is handed (design doc 9.11 (B)).

        Returns the proof, its premises' tokens in order, and its conclusion.
        """
        applied = self.proofs.get(applied_proof_id)
        theorem = self.theorems.get(applied.theorem_id)
        premises = [
            self.proofs._tokens_for_formula(row.formula_id)
            for row in self.proofs._theorem_premise_rows(theorem.id)
        ]
        conclusion = self.proofs._tokens_for_formula(theorem.conclusion_formula_id)
        if not premises:
            return applied, [], conclusion

        target = list(conclusion)
        for tokens in reversed(premises):
            target = self.imp(tokens, target)
        name = f"{theorem.name}_curried"
        curried = self._get_or_create_theorem(name, target, [])
        verified = self._verified_proof_for(curried)
        if verified is not None:
            return verified, premises, conclusion

        steps = self.from_proof_step_specs(
            [
                ProofStepSpec(step_input, tokens)
                for step_input, tokens in self.proofs.reconstruct_steps(applied_proof_id)
            ]
        )
        for index in reversed(range(len(premises))):
            steps = self.discharge(
                steps, target_premise_index=index, discharged_tokens=premises[index]
            )
        proof = self._prove(curried, self.to_proof_step_specs(steps))
        return proof, premises, conclusion

    def _split_implication(self, tokens: list[Token]) -> tuple[list[Token], list[Token]]:
        meta = self.formulas._load_symbol_meta(tokens)
        return decompose_implication_pure(tokens, self.imp_.id, meta)

    def _ks_lift(
        self,
        original: list[DischargeStep],
        discharged_tokens: list[Token],
        *,
        discharged_assumption_ord: int,
        required_ord: int,
    ) -> tuple[list[DischargeStep], dict[int, int], dict[int, int], dict[int, int]]:
        """Lift every line L_i of `original` to `discharged -> L_i`, using only
        K, S and MP/Gen -- i.e. discharge the assumption
        `discharged` by hand, the way the kernel had to before §9.

        Returns the rewritten derivation, a map from each original ordinal to
        the ordinal of its lifted line, a map from each *surviving* assumption's
        original ordinal to its new one, and a map for original lines that are
        still derivable without the discharged assumption.  Tail steps after
        the ⇒intro must use the latter: citing ``L`` after discharge must keep
        citing ``L``, not the lifted ``A -> L``.
        """
        k_axiom = self.axioms.get_by_name("hilbert_k")
        s_axiom = self.axioms.get_by_name("hilbert_s")

        new_steps: list[DischargeStep] = []
        lifted: dict[int, int] = {}
        assumption_map: dict[int, int] = {}
        surviving: dict[int, int] = {}

        required: set[int] = set()

        def require(ord_: int) -> None:
            if ord_ in required:
                return
            required.add(ord_)
            source = original[ord_]
            if source.kind == "mp":
                assert source.mp_left is not None and source.mp_right is not None
                require(source.mp_left)
                require(source.mp_right)
            elif source.kind == "gen":
                assert source.gen_body_ord is not None
                require(source.gen_body_ord)
            elif source.kind == "applied":
                for arg_ord in source.applied_arg_ords:
                    require(arg_ord)

        require(required_ord)

        def add(step: DischargeStep) -> int:
            new_steps.append(step)
            return len(new_steps) - 1

        for i, step in enumerate(original):
            if step.kind == "assumption" and i == discharged_assumption_ord:
                if i not in required:
                    continue
                # A -> A, expanded directly as five K/S/MP lines.  Keeping the
                # derivation inline avoids registering a bundled identity theorem.
                discharged = self._formula(discharged_tokens)
                identity_tokens = self.imp(discharged_tokens, discharged_tokens)
                identity = self._formula(identity_tokens)
                sigma_s = Substitution(
                    prop_substs=(
                        PropSubst(self.phi.id, discharged.id),
                        PropSubst(self.psi.id, identity.id),
                        PropSubst(self.chi.id, discharged.id),
                    )
                )
                s_tokens = self.proofs.compute_substituted_tokens(
                    s_axiom.formula_id, sigma_s
                )
                s_ord = add(
                    DischargeStep(
                        kind="fact",
                        tokens=s_tokens,
                        fact_input=AxiomStepInput(s_axiom.id, sigma_s),
                    )
                )
                sigma_k1 = Substitution(
                    prop_substs=(
                        PropSubst(self.phi.id, discharged.id),
                        PropSubst(self.psi.id, identity.id),
                    )
                )
                k1_tokens = self.proofs.compute_substituted_tokens(
                    k_axiom.formula_id, sigma_k1
                )
                k1_ord = add(
                    DischargeStep(
                        kind="fact",
                        tokens=k1_tokens,
                        fact_input=AxiomStepInput(k_axiom.id, sigma_k1),
                    )
                )
                mid_tokens = self.imp(
                    self.imp(discharged_tokens, identity_tokens), identity_tokens
                )
                mid_ord = add(
                    DischargeStep(
                        kind="mp", tokens=mid_tokens, mp_left=k1_ord, mp_right=s_ord
                    )
                )
                sigma_k2 = Substitution(
                    prop_substs=(
                        PropSubst(self.phi.id, discharged.id),
                        PropSubst(self.psi.id, discharged.id),
                    )
                )
                k2_tokens = self.proofs.compute_substituted_tokens(
                    k_axiom.formula_id, sigma_k2
                )
                k2_ord = add(
                    DischargeStep(
                        kind="fact",
                        tokens=k2_tokens,
                        fact_input=AxiomStepInput(k_axiom.id, sigma_k2),
                    )
                )
                lifted[i] = add(
                    DischargeStep(
                        kind="mp",
                        tokens=identity_tokens,
                        mp_left=k2_ord,
                        mp_right=mid_ord,
                    )
                )
                continue

            if step.kind == "applied":
                assert step.fact_input is not None
                cited = step.fact_input
                assert isinstance(cited, TheoremStepInput)
                curried, premises, conclusion = self.curried_form(cited.applied_proof_id)
                curried_tokens = self.proofs.compute_substituted_tokens(
                    self.theorems.get(curried.theorem_id).conclusion_formula_id,
                    cited.subst,
                )
                if all(arg_ord in surviving for arg_ord in step.applied_arg_ords):
                    surviving[i] = add(
                        replace(
                            step,
                            applied_arg_ords=tuple(
                                surviving[arg_ord] for arg_ord in step.applied_arg_ords
                            ),
                        )
                    )
                if i not in required:
                    continue
                current = add(
                    DischargeStep(
                        kind="fact",
                        tokens=curried_tokens,
                        fact_input=TheoremStepInput(curried.id, cited.subst),
                    )
                )
                # K-lift the curried form, then let S consume one lifted
                # argument at a time: from `A -> (P -> Q)` and `A -> P`, `A -> Q`.
                sigma_k = Substitution(
                    prop_substs=(
                        PropSubst(self.phi.id, self._formula(curried_tokens).id),
                        PropSubst(self.psi.id, self._formula(discharged_tokens).id),
                    )
                )
                k_tokens = self.proofs.compute_substituted_tokens(k_axiom.formula_id, sigma_k)
                k_ord = add(
                    DischargeStep(
                        kind="fact", tokens=k_tokens, fact_input=AxiomStepInput(k_axiom.id, sigma_k)
                    )
                )
                current = add(
                    DischargeStep(
                        kind="mp",
                        tokens=self.imp(discharged_tokens, curried_tokens),
                        mp_left=current,
                        mp_right=k_ord,
                    )
                )
                rest = curried_tokens
                for arg_ord in step.applied_arg_ords:
                    antecedent, consequent = self._split_implication(rest)
                    sigma_s = Substitution(
                        prop_substs=(
                            PropSubst(self.phi.id, self._formula(discharged_tokens).id),
                            PropSubst(self.psi.id, self._formula(antecedent).id),
                            PropSubst(self.chi.id, self._formula(consequent).id),
                        )
                    )
                    s_tokens = self.proofs.compute_substituted_tokens(
                        s_axiom.formula_id, sigma_s
                    )
                    s_ord = add(
                        DischargeStep(
                            kind="fact",
                            tokens=s_tokens,
                            fact_input=AxiomStepInput(s_axiom.id, sigma_s),
                        )
                    )
                    mid = add(
                        DischargeStep(
                            kind="mp",
                            tokens=self.imp(
                                self.imp(discharged_tokens, antecedent),
                                self.imp(discharged_tokens, consequent),
                            ),
                            mp_left=current,
                            mp_right=s_ord,
                        )
                    )
                    current = add(
                        DischargeStep(
                            kind="mp",
                            tokens=self.imp(discharged_tokens, consequent),
                            mp_left=lifted[arg_ord],
                            mp_right=mid,
                        )
                    )
                    rest = consequent
                if rest != step.tokens:
                    raise ValidationError(
                        "_ks_lift: curried form does not reach the cited conclusion"
                    )
                lifted[i] = current
                continue

            if step.kind == "mp":
                assert step.mp_left is not None and step.mp_right is not None
                if step.mp_left in surviving and step.mp_right in surviving:
                    surviving[i] = add(
                        replace(
                            step,
                            mp_left=surviving[step.mp_left],
                            mp_right=surviving[step.mp_right],
                        )
                    )
                if i not in required:
                    continue
                l_left = original[step.mp_left].tokens
                l_i = step.tokens
                left_lifted_ord = lifted[step.mp_left]
                right_lifted_ord = lifted[step.mp_right]
                sigma_s = Substitution(
                    prop_substs=(
                        PropSubst(self.phi.id, self._formula(discharged_tokens).id),
                        PropSubst(self.psi.id, self._formula(l_left).id),
                        PropSubst(self.chi.id, self._formula(l_i).id),
                    )
                )
                s_tokens = self.proofs.compute_substituted_tokens(s_axiom.formula_id, sigma_s)
                s_ord = add(
                    DischargeStep(
                        kind="fact", tokens=s_tokens, fact_input=AxiomStepInput(s_axiom.id, sigma_s)
                    )
                )
                mid_tokens = self.imp(
                    self.imp(discharged_tokens, l_left), self.imp(discharged_tokens, l_i)
                )
                mp1_ord = add(
                    DischargeStep(kind="mp", tokens=mid_tokens, mp_left=right_lifted_ord, mp_right=s_ord)
                )
                lifted_tokens = self.imp(discharged_tokens, l_i)
                mp2_ord = add(
                    DischargeStep(kind="mp", tokens=lifted_tokens, mp_left=left_lifted_ord, mp_right=mp1_ord)
                )
                lifted[i] = mp2_ord
                continue

            if step.kind == "gen":
                assert step.gen_body_ord is not None and step.gen_variable_symbol_id is not None
                gen_var_id = step.gen_variable_symbol_id
                if step.gen_body_ord in surviving:
                    surviving_ord = add(
                        replace(step, gen_body_ord=surviving[step.gen_body_ord])
                    )
                    surviving[i] = surviving_ord
                    if i not in required:
                        continue

                    # If the generalized line is already derivable without the
                    # discharged assumption, lift that independent Gen result
                    # with K.  This is necessary when the assumption contains
                    # the generalized variable: Gen(A(x) -> B) is forbidden,
                    # while Gen(B), followed by K, validly derives
                    # A(x) -> forall x.B.
                    sigma_k = Substitution(
                        prop_substs=(
                            PropSubst(self.phi.id, self._formula(step.tokens).id),
                            PropSubst(
                                self.psi.id,
                                self._formula(discharged_tokens).id,
                            ),
                        )
                    )
                    k_tokens = self.proofs.compute_substituted_tokens(
                        k_axiom.formula_id, sigma_k
                    )
                    k_ord = add(
                        DischargeStep(
                            kind="fact",
                            tokens=k_tokens,
                            fact_input=AxiomStepInput(k_axiom.id, sigma_k),
                        )
                    )
                    lifted[i] = add(
                        DischargeStep(
                            kind="mp",
                            tokens=self.imp(discharged_tokens, step.tokens),
                            mp_left=surviving_ord,
                            mp_right=k_ord,
                        )
                    )
                    continue
                if i not in required:
                    continue
                body_lifted_ord = lifted[step.gen_body_ord]
                context_to_body_tokens = new_steps[body_lifted_ord].tokens
                original_body_tokens = original[step.gen_body_ord].tokens

                symbol_meta = self.formulas._load_symbol_meta(
                    [
                        *context_to_body_tokens,
                        *discharged_tokens,
                        *original_body_tokens,
                        Token(symbol_id=self.forall_.id),
                    ]
                )

                # Gen(gen_var) on "discharged -> body(gen_var)"
                #   -> "forall gen_var (discharged -> body(gen_var))"
                #
                # Recorded as a genuine "gen" DischargeStep (not "fact" with a
                # GenStepInput smuggled in as fact_input): this step is NOT
                # premise-independent in general -- if `original` still has
                # OTHER undischarged premises, `context_to_body_tokens` (and
                # hence this Gen) still depends on them. Keeping the real
                # "gen" kind means a *later* discharge() call over this same
                # output (e.g. discharging a second premise in a second stage)
                # re-enters this branch and correctly rebases `gen_body_ord`
                # via `lifted`, instead of the generic "fact" branch copying a
                # now-stale ordinal verbatim.
                gen_on_lifted_tokens = abstract_and_quantify_pure(
                    context_to_body_tokens, gen_var_id, self.forall_.id, symbol_meta
                )
                gen_ord = add(
                    DischargeStep(
                        kind="gen",
                        tokens=gen_on_lifted_tokens,
                        gen_body_ord=body_lifted_ord,
                        gen_variable_symbol_id=gen_var_id,
                    )
                )

                # hilbert_forall_distribution instance:
                #   forall gen_var (discharged -> body(gen_var))
                #     -> (forall gen_var.discharged -> forall gen_var.body(gen_var))
                # phi1 := discharged (vacuous in gen_var, since discharged_tokens
                # cannot mention the freshly-generalized variable), psi1 := body.
                forall_dist_axiom = self.axioms.get_by_name("hilbert_forall_distribution")
                sigma_dist = Substitution(
                    prop_substs=(
                        PropSubst(self.phi1.id, self._formula(discharged_tokens).id, (gen_var_id,)),
                        PropSubst(self.psi1.id, self._formula(original_body_tokens).id, (gen_var_id,)),
                    )
                )
                dist_tokens = self.proofs.compute_substituted_tokens(
                    forall_dist_axiom.formula_id, sigma_dist
                )
                dist_ord = add(
                    DischargeStep(
                        kind="fact",
                        tokens=dist_tokens,
                        fact_input=AxiomStepInput(forall_dist_axiom.id, sigma_dist),
                    )
                )

                forall_discharged = abstract_and_quantify_pure(
                    discharged_tokens, gen_var_id, self.forall_.id, symbol_meta
                )
                forall_body = abstract_and_quantify_pure(
                    original_body_tokens, gen_var_id, self.forall_.id, symbol_meta
                )
                step2_tokens = self.imp(forall_discharged, forall_body)
                step2_ord = add(
                    DischargeStep(kind="mp", tokens=step2_tokens, mp_left=gen_ord, mp_right=dist_ord)
                )

                # hilbert_forall_const_intro instance: discharged -> forall gen_var.discharged
                forall_const_axiom = self.axioms.get_by_name("hilbert_forall_const_intro")
                sigma_const = Substitution(
                    prop_substs=(PropSubst(self.phi.id, self._formula(discharged_tokens).id),)
                )
                const_tokens = self.proofs.compute_substituted_tokens(
                    forall_const_axiom.formula_id, sigma_const
                )
                const_ord = add(
                    DischargeStep(
                        kind="fact",
                        tokens=const_tokens,
                        fact_input=AxiomStepInput(forall_const_axiom.id, sigma_const),
                    )
                )

                # compose: (discharged -> forall.discharged), (forall.discharged -> forall.body)
                #   -> discharged -> forall.body
                final_ord = self.compose_imp_d(
                    new_steps, const_ord, discharged_tokens, forall_discharged, step2_ord, forall_body
                )
                lifted[i] = final_ord
                continue

            if step.kind == "premise":
                source_ord = add(step)
                surviving[i] = source_ord
                source_tokens = step.tokens
            elif step.kind == "assumption":
                # Some *other* formula's assumption: it stays open here, so an
                # enclosing ⇒intro can still close it.
                source_ord = add(step)
                assumption_map[i] = source_ord
                surviving[i] = source_ord
                source_tokens = step.tokens
            elif step.kind == "fact":
                source_ord = add(
                    DischargeStep(kind="fact", tokens=step.tokens, fact_input=step.fact_input)
                )
                surviving[i] = source_ord
                source_tokens = step.tokens
            else:
                raise NotImplementedError(f"_ks_lift: unsupported step kind {step.kind!r}")

            if i not in required:
                continue

            sigma_k = Substitution(
                prop_substs=(
                    PropSubst(self.phi.id, self._formula(source_tokens).id),
                    PropSubst(self.psi.id, self._formula(discharged_tokens).id),
                )
            )
            k_tokens = self.proofs.compute_substituted_tokens(k_axiom.formula_id, sigma_k)
            k_ord = add(
                DischargeStep(kind="fact", tokens=k_tokens, fact_input=AxiomStepInput(k_axiom.id, sigma_k))
            )
            lifted_tokens = self.imp(discharged_tokens, source_tokens)
            mp_ord = add(
                DischargeStep(kind="mp", tokens=lifted_tokens, mp_left=source_ord, mp_right=k_ord)
            )
            lifted[i] = mp_ord

        return new_steps, lifted, assumption_map, surviving

    def to_proof_step_specs(self, steps: list[DischargeStep]) -> list[ProofStepSpec]:
        specs: list[ProofStepSpec] = []
        for step in steps:
            if step.kind == "premise":
                assert step.premise_index is not None
                specs.append(ProofStepSpec(PremiseStepInput(step.premise_index), step.tokens))
            elif step.kind == "mp":
                assert step.mp_left is not None and step.mp_right is not None
                specs.append(
                    ProofStepSpec(MPStepInput(step.mp_left, step.mp_right), step.tokens)
                )
            elif step.kind == "gen":
                assert step.gen_body_ord is not None and step.gen_variable_symbol_id is not None
                specs.append(
                    ProofStepSpec(
                        GenStepInput(step.gen_body_ord, step.gen_variable_symbol_id), step.tokens
                    )
                )
            elif step.kind == "assumption":
                specs.append(ProofStepSpec(AssumptionStepInput(), step.tokens))
            elif step.kind == "imp_intro":
                assert step.imp_assumption_ord is not None and step.imp_body_ord is not None
                specs.append(
                    ProofStepSpec(
                        ImplicationIntroStepInput(step.imp_assumption_ord, step.imp_body_ord),
                        step.tokens,
                    )
                )
            elif step.kind == "applied":
                # Its argument ordinals live in `applied_arg_ords`, which the
                # renumbering keeps current -- the stashed input's own copy does
                # not, so rebuild it rather than emitting it verbatim.
                assert isinstance(step.fact_input, TheoremStepInput)
                specs.append(
                    ProofStepSpec(
                        TheoremStepInput(
                            step.fact_input.applied_proof_id,
                            step.fact_input.subst,
                            tuple(step.applied_arg_ords),
                        ),
                        step.tokens,
                    )
                )
            else:
                assert step.fact_input is not None
                specs.append(ProofStepSpec(step.fact_input, step.tokens))
        return specs

    def from_proof_step_specs(self, specs: list[ProofStepSpec]) -> list[DischargeStep]:
        """Inverse of `to_proof_step_specs`, so a derivation already written as
        `ProofStepSpec`s (e.g. a seeder's own theorem-with-premise proof) can
        be fed into `discharge` without duplicating its construction. Every
        step's `conclusion_tokens` must already be `list[Token]` (not a
        pinned formula id).  A `TheoremStepInput` with non-empty
        `arg_step_ords` becomes an "applied" step: it used to be rejected here
        because `_ks_lift` had no way to lift it, which is what §5 rule 12 was
        working around.  It does now (design doc 9.11 (B))."""
        steps: list[DischargeStep] = []
        for spec in specs:
            tokens = spec.conclusion_tokens
            assert isinstance(tokens, list), "from_proof_step_specs requires literal token lists"
            if isinstance(spec.input, PremiseStepInput):
                steps.append(DischargeStep(kind="premise", tokens=tokens, premise_index=spec.input.premise_ord))
            elif isinstance(spec.input, MPStepInput):
                steps.append(
                    DischargeStep(
                        kind="mp",
                        tokens=tokens,
                        mp_left=spec.input.antecedent_step_ord,
                        mp_right=spec.input.implication_step_ord,
                    )
                )
            elif isinstance(spec.input, GenStepInput):
                steps.append(
                    DischargeStep(
                        kind="gen",
                        tokens=tokens,
                        gen_body_ord=spec.input.body_step_ord,
                        gen_variable_symbol_id=spec.input.gen_variable_symbol_id,
                    )
                )
            elif isinstance(spec.input, AssumptionStepInput):
                steps.append(DischargeStep(kind="assumption", tokens=tokens))
            elif isinstance(spec.input, ImplicationIntroStepInput):
                steps.append(
                    DischargeStep(
                        kind="imp_intro",
                        tokens=tokens,
                        imp_assumption_ord=spec.input.assumption_step_ord,
                        imp_body_ord=spec.input.body_step_ord,
                    )
                )
            elif isinstance(spec.input, TheoremStepInput) and spec.input.arg_step_ords:
                steps.append(
                    DischargeStep(
                        kind="applied",
                        tokens=tokens,
                        fact_input=spec.input,
                        applied_arg_ords=tuple(spec.input.arg_step_ords),
                    )
                )
            else:
                steps.append(DischargeStep(kind="fact", tokens=tokens, fact_input=spec.input))
        return steps

    # -- small K/S composition helpers ---------------------------------------

    def compose_imp(
        self,
        steps: list[ProofStepSpec],
        f_ord: int,
        a_tokens: list[Token],
        b_tokens: list[Token],
        g_ord: int,
        c_tokens: list[Token],
    ) -> int:
        """Compose A→B and B→C using only K, S and MP."""
        lifted_g = self.klift(steps, g_ord, self.imp(b_tokens, c_tokens), a_tokens)
        return self.scombine(
            steps, a_tokens, lifted_g, b_tokens, c_tokens, f_ord
        )

    def klift(
        self,
        steps: list[ProofStepSpec],
        fact_ord: int,
        fact_tokens: list[Token],
        context_tokens: list[Token],
    ) -> int:
        """Given a premise-independent fact F (at fact_ord), appends steps
        proving `context -> F`; returns the new ordinal."""
        k_axiom = self.axioms.get_by_name("hilbert_k")
        sigma_k = Substitution(
            prop_substs=(
                PropSubst(self.phi.id, self._formula(fact_tokens).id),
                PropSubst(self.psi.id, self._formula(context_tokens).id),
            )
        )
        k_tokens = self.proofs.compute_substituted_tokens(k_axiom.formula_id, sigma_k)
        steps.append(ProofStepSpec(AxiomStepInput(k_axiom.id, sigma_k), k_tokens))
        k_ord = len(steps) - 1
        lifted_tokens = self.imp(context_tokens, fact_tokens)
        steps.append(ProofStepSpec(MPStepInput(fact_ord, k_ord), lifted_tokens))
        return len(steps) - 1

    def scombine(
        self,
        steps: list[ProofStepSpec],
        context_tokens: list[Token],
        f_ord: int,
        a_tokens: list[Token],
        b_tokens: list[Token],
        g_ord: int,
    ) -> int:
        """Given F: context->(A->B) (at f_ord) and G: context->A (at
        g_ord), appends steps proving `context -> B`; returns the new
        ordinal."""
        s_axiom = self.axioms.get_by_name("hilbert_s")
        sigma_s = Substitution(
            prop_substs=(
                PropSubst(self.phi.id, self._formula(context_tokens).id),
                PropSubst(self.psi.id, self._formula(a_tokens).id),
                PropSubst(self.chi.id, self._formula(b_tokens).id),
            )
        )
        s_tokens = self.proofs.compute_substituted_tokens(s_axiom.formula_id, sigma_s)
        steps.append(ProofStepSpec(AxiomStepInput(s_axiom.id, sigma_s), s_tokens))
        s_ord = len(steps) - 1
        steps.append(
            ProofStepSpec(
                MPStepInput(f_ord, s_ord),
                self.imp(self.imp(context_tokens, a_tokens), self.imp(context_tokens, b_tokens)),
            )
        )
        mid_ord = len(steps) - 1
        steps.append(ProofStepSpec(MPStepInput(g_ord, mid_ord), self.imp(context_tokens, b_tokens)))
        return len(steps) - 1

    def compose_imp_d(
        self,
        steps: list[DischargeStep],
        f_ord: int,
        a_tokens: list[Token],
        b_tokens: list[Token],
        g_ord: int,
        c_tokens: list[Token],
    ) -> int:
        """Compose A→B and B→C as raw K/S `DischargeStep` values."""
        k_axiom = self.axioms.get_by_name("hilbert_k")
        s_axiom = self.axioms.get_by_name("hilbert_s")
        b_to_c = self.imp(b_tokens, c_tokens)
        sigma_k = Substitution(
            prop_substs=(
                PropSubst(self.phi.id, self._formula(b_to_c).id),
                PropSubst(self.psi.id, self._formula(a_tokens).id),
            )
        )
        k_tokens = self.proofs.compute_substituted_tokens(
            k_axiom.formula_id, sigma_k
        )
        steps.append(
            DischargeStep(
                kind="fact",
                tokens=k_tokens,
                fact_input=AxiomStepInput(k_axiom.id, sigma_k),
            )
        )
        k_ord = len(steps) - 1
        steps.append(
            DischargeStep(
                kind="mp",
                tokens=self.imp(a_tokens, b_to_c),
                mp_left=g_ord,
                mp_right=k_ord,
            )
        )
        lifted_g = len(steps) - 1
        sigma_s = Substitution(
            prop_substs=(
                PropSubst(self.phi.id, self._formula(a_tokens).id),
                PropSubst(self.psi.id, self._formula(b_tokens).id),
                PropSubst(self.chi.id, self._formula(c_tokens).id),
            )
        )
        s_tokens = self.proofs.compute_substituted_tokens(
            s_axiom.formula_id, sigma_s
        )
        steps.append(
            DischargeStep(
                kind="fact",
                tokens=s_tokens,
                fact_input=AxiomStepInput(s_axiom.id, sigma_s),
            )
        )
        s_ord = len(steps) - 1
        steps.append(
            DischargeStep(
                kind="mp",
                tokens=self.imp(
                    self.imp(a_tokens, b_tokens), self.imp(a_tokens, c_tokens)
                ),
                mp_left=lifted_g,
                mp_right=s_ord,
            )
        )
        mid_ord = len(steps) - 1
        steps.append(
            DischargeStep(
                kind="mp",
                tokens=self.imp(a_tokens, c_tokens),
                mp_left=f_ord,
                mp_right=mid_ord,
            )
        )
        return len(steps) - 1

    # -- shared plumbing --------------------------------------------------

    def _get_or_create_theorem(
        self,
        name: str,
        conclusion_tokens: list[Token],
        premise_tokens: list[list[Token]],
    ) -> Theorem:
        conclusion = self._formula(
            conclusion_tokens,
            remarks=theorem_conclusion_formula_remark(name),
        )
        premises = [
            self._formula(tokens, remarks=theorem_premise_formula_remark(name, index))
            for index, tokens in enumerate(premise_tokens)
        ]
        existing = self.session.scalar(
            select(Theorem).where(Theorem.name == name)
        )
        if existing is not None:
            premise_ids = list(
                self.session.scalars(
                    select(TheoremPremise.formula_id)
                    .where(TheoremPremise.theorem_id == existing.id)
                    .order_by(TheoremPremise.ord)
                )
            )
            expected_ids = [formula.id for formula in premises]
            if existing.conclusion_formula_id != conclusion.id or premise_ids != expected_ids:
                raise ValidationError(f"existing theorem {name!r} has a different statement")
            existing.remarks = "ImpIntro 除去手続きが生成したカリー化定理"
            self.session.flush()
            return existing

        return self.theorems.register(
            name=name,
            conclusion_formula_id=conclusion.id,
            premise_formula_ids=[formula.id for formula in premises],
            remarks="ImpIntro 除去手続きが生成したカリー化定理",
        )

    def _prove(self, theorem: Theorem, steps: Sequence[ProofStepSpec]) -> Proof:
        verified = self._verified_proof_for(theorem)
        if verified is not None:
            if theorem.status != "proven":
                self.theorems._promote_to_proven(theorem.id)
            return verified

        proof = self.proofs.create_proof(
            theorem.id,
            name=seed_proof_name(theorem.name),
            remarks="ImpIntro 除去手続きが生成した導出証明",
        )
        for step in steps:
            conclusion_formula = self._coerce_formula(step.conclusion_tokens)
            self.proofs.add_step(proof.id, step.input, conclusion_formula.id)
        self.proofs.validate(proof.id)
        return proof

    def _verified_proof_for(self, theorem: Theorem) -> Proof | None:
        for proof in self.proofs.list_for_theorem(theorem.id):
            if proof.status == "verified":
                return proof
        return None

    def _coerce_formula(self, value: list[Token] | int) -> Formula:
        if isinstance(value, int):
            return self.formulas.get(value)
        return self._formula(value)

    def _formula(self, tokens: list[Token], remarks: str | None = None) -> Formula:
        formula = self.formulas.register(tokens, remarks=remarks)
        if remarks is not None and formula.remarks != remarks:
            formula.remarks = remarks
        return formula
