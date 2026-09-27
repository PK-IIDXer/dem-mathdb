from __future__ import annotations

from collections.abc import Sequence
from collections import defaultdict
from dataclasses import dataclass
from typing import TypeAlias

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session, joinedload

from dem.db.models.inference import Axiom, AxiomSystem, AxiomSystemMember, InferenceRule
from dem.db.models.language import Formula, FormulaToken, Symbol, SymbolType
from dem.db.models.theorem import (
    Proof,
    ProofIdentitySequence,
    ProofStep,
    ProofStepArg,
    ProofStepSubstProp,
    ProofStepSubstPropParam,
    ProofStepSubstTerm,
    Theorem,
    TheoremPremise,
)
from dem.errors import NotFoundError, ProofValidationError, ValidationError
from dem.services.authoring_provenance import AuthoringVia, record_authoring_provenance
from dem.identity import deterministic_public_id
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService, match_theorem_constraints
from dem.services.used_axioms import is_defining_axiom, used_axiom_ids_for_proof
from dem.types import (
    AssumptionStepInput,
    AxiomStepInput,
    FormulaTypeName,
    GenStepInput,
    ImplicationIntroStepInput,
    MPStepInput,
    PremiseStepInput,
    PropSubst,
    ProofStepInput,
    Substitution,
    SymbolMeta,
    SymbolTypeName,
    TermSubst,
    TheoremStepInput,
    Token,
)
from demlang.match import MatchResult, PropBinding


@dataclass(frozen=True)
class StepData:
    ord: int
    step_kind: str
    conclusion_tokens: list[Token]
    premise_ord: int | None = None
    axiom_tokens: list[Token] | None = None
    applied_proof_status: str | None = None
    applied_theorem_conclusion_tokens: list[Token] | None = None
    applied_theorem_premise_tokens_list: list[list[Token]] | None = None
    prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]] | None = None
    term_subst: dict[int, list[Token]] | None = None
    arg_step_ords: list[int] | None = None
    gen_variable_symbol_id: int | None = None
    inference_rule_kind: str | None = None


# A step's judgement is a sequent `Γ' ⊢ P`, and `Γ'` is tracked as a set of
# dependency keys. A theorem premise is keyed by its ordinal in the theorem's
# premise list; a local `assumption` step is keyed by the assumed formula
# itself, so several assumption steps of the same proposition share one key and
# a single `implication_intro` discharges all of them at once.
DepKey: TypeAlias = tuple[str, int] | tuple[str, tuple[Token, ...]]

_PREMISE = "premise"
_ASSUMPTION = "assumption"

# The rule kinds a "raw" proof may use: the primitives, plus ⇒introduction,
# which is admissible rather than primitive but carries an elimination
# procedure back to the primitives (design doc §9.4/§9.5). Anything else is a
# trusted recognizer, and a proof citing one is not raw.
RAW_INFERENCE_RULE_KINDS = frozenset(
    {"modus_ponens", "generalization", "implication_intro"}
)


def premise_dep(premise_ord: int) -> DepKey:
    return (_PREMISE, premise_ord)


def assumption_dep(tokens: Sequence[Token]) -> DepKey:
    return (_ASSUMPTION, tuple(tokens))


@dataclass(frozen=True)
class StepJudgement:
    tokens: list[Token]
    premise_deps: frozenset[DepKey]


@dataclass(frozen=True)
class ProofStatePremise:
    ord: int
    tokens: list[Token]
    used_by: list[int]


@dataclass(frozen=True)
class ProofStateEstablished:
    ord: int
    tokens: list[Token]
    step_kind: str
    depends_on_premises: list[int]
    depends_on_assumptions: list[int]


@dataclass(frozen=True)
class ProofStateOpenAssumption:
    step_ord: int
    tokens: list[Token]


@dataclass(frozen=True)
class ProofState:
    goal_tokens: list[Token]
    premises: list[ProofStatePremise]
    established: list[ProofStateEstablished]
    open_assumptions: list[ProofStateOpenAssumption]
    reached_goal: bool
    blocking: list[str]


@dataclass(frozen=True)
class ProofStepFollowup:
    kind: str
    antecedent_step_ord: int
    implication_step_ord: int
    conclusion_tokens: list[Token]
    reaches_goal: bool


@dataclass(frozen=True)
class BackwardStepSuggestion:
    match_depth: int
    applied_proof_id: int | None
    subst: Substitution
    undetermined: list[dict[str, object]]
    defaulted_to_identity: list[int]
    application_conclusion_tokens: list[Token]
    antecedent_goals: list[list[Token]]
    intermediate_conclusions: list[list[Token]]
    premise_count: int
    premise_goals: list[list[Token]]
    arg_candidates: list[list[int]]


def _mismatch_details(expected: list[Token], actual: list[Token],
                      symbol_meta: dict[int, SymbolMeta]) -> dict[str, object]:
    def first_difference(left: int, right: int, path: list[int]) -> list[int] | None:
        if left >= len(expected) or right >= len(actual) or expected[left] != actual[right]:
            return path
        token = expected[left]
        arity = symbol_meta[token.symbol_id].arity if token.is_symbol else 0
        left += 1
        right += 1
        for child in range(arity):
            difference = first_difference(left, right, [*path, child])
            if difference is not None:
                return difference
            left = _subtree_end(expected, left, symbol_meta)
            right = _subtree_end(actual, right, symbol_meta)
        return None

    return {"expected": expected, "actual": actual,
            "diff_path": first_difference(0, 0, []) or []}


def apply_substitution_pure(
    formula_tokens: Sequence[Token],
    prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]],
    term_subst: dict[int, list[Token]],
    symbol_meta: dict[int, SymbolMeta],
) -> list[Token]:
    after_prop = _replace_prop_vars(tuple(formula_tokens), 0, 0, prop_subst, symbol_meta)[0]
    after_term = _replace_term_vars(tuple(after_prop), 0, 0, term_subst, symbol_meta)[0]
    return after_term


def abstract_and_quantify_pure(
    body_tokens: Sequence[Token],
    variable_symbol_id: int,
    forall_symbol_id: int,
    symbol_meta: dict[int, SymbolMeta],
) -> list[Token]:
    abstracted, next_pos = _abstract_tokens(
        tuple(body_tokens), 0, 0, variable_symbol_id, symbol_meta
    )
    if next_pos != len(body_tokens):
        raise ValidationError("cannot abstract malformed token sequence")
    return [Token(symbol_id=forall_symbol_id), *abstracted]


def _materialize_miller_body(
    binding: PropBinding,
    formal_symbol_id: int,
    symbol_meta: dict[int, SymbolMeta],
) -> list[Token]:
    """Open the one surrounding binder as a free formal parameter."""
    if binding.parameter_de_bruijn_index is None:
        return list(binding.body_tokens)

    def visit(pos: int, local_depth: int) -> tuple[list[Token], int]:
        if pos >= len(binding.body_tokens):
            raise ValueError("unexpected end of Miller body")
        token = binding.body_tokens[pos]
        if token.is_bound_var:
            index = token.de_bruijn_index or 0
            expected = binding.parameter_de_bruijn_index + local_depth
            if index == expected:
                return [Token(symbol_id=formal_symbol_id)], pos + 1
            if index >= local_depth:
                raise ValueError("Miller body refers to another outer binder")
            return [token], pos + 1
        meta = symbol_meta[token.symbol_id or 0]
        output = [token]
        pos += 1
        child_depth = local_depth + 1 if meta.is_quantifier else local_depth
        for _ in range(1 if meta.is_quantifier else meta.arity):
            child, pos = visit(pos, child_depth)
            output.extend(child)
        return output, pos

    body, end = visit(0, 0)
    if end != len(binding.body_tokens):
        raise ValueError("trailing tokens in Miller body")
    return body


def validate_proof_steps(
    goal_tokens: list[Token],
    premise_tokens_list: list[list[Token]],
    steps_data: list[StepData],
    symbol_meta: dict[int, SymbolMeta],
    implication_symbol_id: int,
    forall_symbol_id: int,
) -> None:
    if not steps_data:
        raise ProofValidationError("proof has no steps", code="proof.empty")

    prior: dict[int, StepJudgement] = {}
    assumption_tokens: dict[int, list[Token]] = {}
    for step in steps_data:
        derived = validate_proof_step(
            step=step,
            prior=prior,
            premise_tokens_list=premise_tokens_list,
            symbol_meta=symbol_meta,
            implication_symbol_id=implication_symbol_id,
            forall_symbol_id=forall_symbol_id,
            assumption_tokens=assumption_tokens,
        )
        if derived.tokens != step.conclusion_tokens:
            raise ProofValidationError("step conclusion mismatch", step.ord, code="proof.step_conclusion_mismatch", details=_mismatch_details(derived.tokens, step.conclusion_tokens, symbol_meta))
        if step.step_kind == _ASSUMPTION:
            assumption_tokens[step.ord] = derived.tokens
        prior[step.ord] = derived

    final = prior[steps_data[-1].ord]
    if final.tokens != goal_tokens:
        raise ProofValidationError("final step does not match theorem conclusion", steps_data[-1].ord, code="proof.final_mismatch")
    # A local assumption only ever pays for itself through implication_intro;
    # letting one survive into the conclusion would prove the theorem from an
    # assumption the theorem does not declare.
    if any(kind == _ASSUMPTION for kind, _ in final.premise_deps):
        raise ProofValidationError(
            "final step still depends on an undischarged assumption", steps_data[-1].ord, code="proof.open_assumption")


def validate_proof_step(
    step: StepData,
    prior: dict[int, StepJudgement],
    premise_tokens_list: list[list[Token]],
    symbol_meta: dict[int, SymbolMeta],
    implication_symbol_id: int,
    forall_symbol_id: int,
    assumption_tokens: dict[int, list[Token]] | None = None,
) -> StepJudgement:
    arg_step_ords = step.arg_step_ords or []
    prop_subst = step.prop_subst or {}
    term_subst = step.term_subst or {}
    assumptions = assumption_tokens or {}

    if step.step_kind == "premise":
        if step.premise_ord is None or step.premise_ord < 0 or step.premise_ord >= len(premise_tokens_list):
            raise ProofValidationError("premise_ord out of range", step.ord, code="proof.premise_ord_range")
        if arg_step_ords:
            raise ProofValidationError("premise step must not have args", step.ord, code="proof.step_takes_no_args")
        return StepJudgement(
            premise_tokens_list[step.premise_ord], frozenset({premise_dep(step.premise_ord)})
        )

    if step.step_kind == _ASSUMPTION:
        if arg_step_ords:
            raise ProofValidationError("assumption step must not have args", step.ord, code="proof.step_takes_no_args")
        return StepJudgement(
            step.conclusion_tokens, frozenset({assumption_dep(step.conclusion_tokens)})
        )

    if step.step_kind == "axiom":
        if step.axiom_tokens is None:
            raise ProofValidationError("axiom step missing axiom formula", step.ord, code="proof.missing_step_data")
        if arg_step_ords:
            raise ProofValidationError("axiom step must not have args", step.ord, code="proof.step_takes_no_args")
        return StepJudgement(
            apply_substitution_pure(step.axiom_tokens, prop_subst, term_subst, symbol_meta),
            frozenset(),
        )

    if step.step_kind == "theorem":
        if step.applied_proof_status != "verified":
            raise ProofValidationError("applying an unverified proof", step.ord, code="proof.unverified_citation")
        if (
            step.applied_theorem_conclusion_tokens is None
            or step.applied_theorem_premise_tokens_list is None
        ):
            raise ProofValidationError("theorem step missing pinned theorem data", step.ord, code="proof.missing_step_data")
        instantiated_premises = [
            apply_substitution_pure(tokens, prop_subst, term_subst, symbol_meta)
            for tokens in step.applied_theorem_premise_tokens_list
        ]
        if len(arg_step_ords) != len(instantiated_premises):
            raise ProofValidationError("theorem arg count mismatch", step.ord, code="proof.arg_count")
        premise_deps: set[int] = set()
        for arg_index, referenced_ord in enumerate(arg_step_ords):
            referenced = _prior_or_fail(prior, referenced_ord, step.ord)
            premise_deps.update(referenced.premise_deps)
            if referenced.tokens != instantiated_premises[arg_index]:
                raise ProofValidationError(
                    f"theorem arg {arg_index} does not match instantiated premise",
                    step.ord, code="proof.arg_mismatch", details={"arg_index": arg_index, "expected": instantiated_premises[arg_index], "actual": referenced.tokens})
        return StepJudgement(
            apply_substitution_pure(
                step.applied_theorem_conclusion_tokens, prop_subst, term_subst, symbol_meta
            ),
            frozenset(premise_deps),
        )

    if step.step_kind == "rule":
        if step.inference_rule_kind == "modus_ponens":
            if len(arg_step_ords) != 2:
                raise ProofValidationError("MP requires 2 args", step.ord, code="proof.rule_arity")
            antecedent = _prior_or_fail(prior, arg_step_ords[0], step.ord)
            implication = _prior_or_fail(prior, arg_step_ords[1], step.ord)
            imp_antecedent, consequent = decompose_implication_pure(
                implication.tokens, implication_symbol_id, symbol_meta
            )
            if antecedent.tokens != imp_antecedent:
                raise ProofValidationError("MP antecedent mismatch", step.ord, code="proof.mp_antecedent_mismatch", details={"expected": imp_antecedent, "actual": antecedent.tokens})
            return StepJudgement(
                consequent,
                antecedent.premise_deps | implication.premise_deps,
            )

        if step.inference_rule_kind == "generalization":
            if len(arg_step_ords) != 1:
                raise ProofValidationError("Gen requires 1 arg", step.ord, code="proof.rule_arity")
            if step.gen_variable_symbol_id is None:
                raise ProofValidationError("Gen requires gen_variable_symbol_id", step.ord, code="proof.gen_variable_missing")
            body = _prior_or_fail(prior, arg_step_ords[0], step.ord)
            for kind, key in body.premise_deps:
                if kind == _PREMISE:
                    open_tokens: Sequence[Token] = premise_tokens_list[key]
                    message = "Gen variable is free in a theorem premise"
                else:
                    open_tokens = key
                    message = "Gen variable is free in an open assumption"
                if has_free_occurrence(open_tokens, step.gen_variable_symbol_id):
                    raise ProofValidationError(message, step.ord, code=("proof.gen_variable_in_premise" if kind == _PREMISE else "proof.gen_variable_in_assumption"), details={"variable_symbol_id": step.gen_variable_symbol_id, **({"premise_ord": key} if kind == _PREMISE else {})})
            return StepJudgement(
                abstract_and_quantify_pure(
                    body.tokens, step.gen_variable_symbol_id, forall_symbol_id, symbol_meta
                ),
                body.premise_deps,
            )

        if step.inference_rule_kind == "implication_intro":
            # Γ ∪ {A} ⊢ Q  /  Γ ⊢ A ⇒ Q. The only rule in the kernel that
            # *shrinks* premise_deps; see design doc §9.3.
            if len(arg_step_ords) != 2:
                raise ProofValidationError("=>intro requires 2 args", step.ord, code="proof.rule_arity")
            assumption_ord, body_ord = arg_step_ords
            assumed = assumptions.get(assumption_ord)
            if assumed is None:
                raise ProofValidationError(
                    "=>intro arg 0 must reference an assumption step", step.ord, code="proof.intro_not_assumption")
            body = _prior_or_fail(prior, body_ord, step.ord)
            return StepJudgement(
                [Token(symbol_id=implication_symbol_id), *assumed, *body.tokens],
                body.premise_deps - {assumption_dep(assumed)},
            )

        raise ProofValidationError("unknown inference rule kind", step.ord, code="proof.unknown_kind")

    raise ProofValidationError(f"unknown step kind: {step.step_kind}", step.ord, code="proof.unknown_kind")


def decompose_implication_pure(
    tokens: Sequence[Token],
    implication_symbol_id: int,
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], list[Token]]:
    if not tokens or tokens[0] != Token(symbol_id=implication_symbol_id):
        raise ProofValidationError("MP second arg is not an implication", code="proof.mp_not_implication")
    left_end = _subtree_end(tokens, 1, symbol_meta)
    right_end = _subtree_end(tokens, left_end, symbol_meta)
    if right_end != len(tokens):
        raise ProofValidationError("implication has trailing tokens", code="proof.trailing_tokens")
    return list(tokens[1:left_end]), list(tokens[left_end:right_end])


def has_free_occurrence(tokens: Sequence[Token], symbol_id: int) -> bool:
    return any(token.symbol_id == symbol_id for token in tokens if token.is_symbol)


def _prior_or_fail(
    prior: dict[int, StepJudgement], referenced_ord: int, step_ord: int
) -> StepJudgement:
    try:
        return prior[referenced_ord]
    except KeyError as exc:
        raise ProofValidationError("arg references an unavailable prior step", step_ord, code="proof.bad_step_reference") from exc


def _replace_prop_vars(
    tokens: Sequence[Token],
    pos: int,
    depth: int,
    prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]],
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], int]:
    if pos >= len(tokens):
        raise ValidationError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        return [token], pos + 1

    symbol_id = _symbol_id(token)
    meta = symbol_meta[symbol_id]
    if meta.symbol_type_name == SymbolTypeName.FREE_PROP_VAR and symbol_id in prop_subst:
        args: list[list[Token]] = []
        cur = pos + 1
        for _ in range(meta.arity):
            arg, cur = _replace_prop_vars(tokens, cur, depth, prop_subst, symbol_meta)
            args.append(arg)
        body_tokens, formal_params = prop_subst[symbol_id]
        if len(formal_params) != meta.arity:
            raise ValidationError("proposition substitution arity mismatch")
        instantiated = _replace_formal_params(tuple(body_tokens), 0, 0, formal_params, args, symbol_meta)[0]
        return instantiated, cur

    output = [token]
    cur = pos + 1
    if meta.is_quantifier:
        child, cur = _replace_prop_vars(tokens, cur, depth + 1, prop_subst, symbol_meta)
        output.extend(child)
        return output, cur

    for _ in range(meta.arity):
        child, cur = _replace_prop_vars(tokens, cur, depth, prop_subst, symbol_meta)
        output.extend(child)
    return output, cur


def _replace_formal_params(
    tokens: Sequence[Token],
    pos: int,
    depth: int,
    formal_params: tuple[int, ...],
    args: Sequence[Sequence[Token]],
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], int]:
    if pos >= len(tokens):
        raise ValidationError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        return [token], pos + 1

    symbol_id = _symbol_id(token)
    meta = symbol_meta[symbol_id]
    if meta.symbol_type_name == SymbolTypeName.FREE_TERM_VAR and symbol_id in formal_params:
        arg_index = formal_params.index(symbol_id)
        return _shift_free_de_bruijn(args[arg_index], depth, symbol_meta), pos + 1

    output = [token]
    cur = pos + 1
    child_depth = depth + 1 if meta.is_quantifier else depth
    for _ in range(1 if meta.is_quantifier else meta.arity):
        child, cur = _replace_formal_params(
            tokens, cur, child_depth, formal_params, args, symbol_meta
        )
        output.extend(child)
    return output, cur


def _replace_term_vars(
    tokens: Sequence[Token],
    pos: int,
    depth: int,
    term_subst: dict[int, list[Token]],
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], int]:
    if pos >= len(tokens):
        raise ValidationError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        return [token], pos + 1

    symbol_id = _symbol_id(token)
    meta = symbol_meta[symbol_id]
    if meta.symbol_type_name == SymbolTypeName.FREE_TERM_VAR and symbol_id in term_subst:
        return _shift_free_de_bruijn(term_subst[symbol_id], depth, symbol_meta), pos + 1

    output = [token]
    cur = pos + 1
    if meta.is_quantifier:
        child, cur = _replace_term_vars(tokens, cur, depth + 1, term_subst, symbol_meta)
        output.extend(child)
        return output, cur

    for _ in range(meta.arity):
        child, cur = _replace_term_vars(tokens, cur, depth, term_subst, symbol_meta)
        output.extend(child)
    return output, cur


def _abstract_tokens(
    tokens: Sequence[Token],
    pos: int,
    depth: int,
    variable_symbol_id: int,
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], int]:
    if pos >= len(tokens):
        raise ValidationError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        return [token], pos + 1

    symbol_id = _symbol_id(token)
    meta = symbol_meta[symbol_id]
    if meta.symbol_type_name == SymbolTypeName.FREE_TERM_VAR and symbol_id == variable_symbol_id:
        return [Token(de_bruijn_index=depth)], pos + 1

    output = [token]
    cur = pos + 1
    if meta.is_quantifier:
        child, cur = _abstract_tokens(tokens, cur, depth + 1, variable_symbol_id, symbol_meta)
        output.extend(child)
        return output, cur

    for _ in range(meta.arity):
        child, cur = _abstract_tokens(tokens, cur, depth, variable_symbol_id, symbol_meta)
        output.extend(child)
    return output, cur


def _shift_free_de_bruijn(
    tokens: Sequence[Token], amount: int, symbol_meta: dict[int, SymbolMeta]
) -> list[Token]:
    shifted, next_pos = _shift_tokens(tokens, 0, 0, amount, symbol_meta)
    if next_pos != len(tokens):
        raise ValidationError("cannot shift malformed token sequence")
    return shifted


def _shift_tokens(
    tokens: Sequence[Token],
    pos: int,
    cutoff: int,
    amount: int,
    symbol_meta: dict[int, SymbolMeta],
) -> tuple[list[Token], int]:
    if pos >= len(tokens):
        raise ValidationError("unexpected end of tokens")
    token = tokens[pos]
    if token.is_bound_var:
        index = _bound_index(token)
        if index >= cutoff:
            return [Token(de_bruijn_index=index + amount)], pos + 1
        return [token], pos + 1

    symbol_id = _symbol_id(token)
    meta = symbol_meta[symbol_id]
    output = [token]
    cur = pos + 1
    if meta.is_quantifier:
        child, cur = _shift_tokens(tokens, cur, cutoff + 1, amount, symbol_meta)
        output.extend(child)
        return output, cur

    for _ in range(meta.arity):
        child, cur = _shift_tokens(tokens, cur, cutoff, amount, symbol_meta)
        output.extend(child)
    return output, cur


def _subtree_end(tokens: Sequence[Token], pos: int, symbol_meta: dict[int, SymbolMeta]) -> int:
    if pos >= len(tokens):
        raise ProofValidationError("unexpected end of tokens while parsing subtree", code="proof.unexpected_end")
    token = tokens[pos]
    if token.is_bound_var:
        return pos + 1
    meta = symbol_meta[_symbol_id(token)]
    cur = pos + 1
    child_count = 1 if meta.is_quantifier else meta.arity
    for _ in range(child_count):
        cur = _subtree_end(tokens, cur, symbol_meta)
    return cur


def _symbol_id(token: Token) -> int:
    if token.symbol_id is None:
        raise AssertionError("token is not a symbol")
    return token.symbol_id


def _bound_index(token: Token) -> int:
    if token.de_bruijn_index is None:
        raise AssertionError("token is not a bound variable")
    return token.de_bruijn_index


@dataclass
class _ProofPrefix:
    next_ord: int
    prior: dict[int, StepJudgement]
    assumptions: dict[int, list[Token]]
    premises: list[list[Token]]
    symbol_meta: dict[int, SymbolMeta]
    implication_id: int
    forall_id: int


@event.listens_for(Session, "after_soft_rollback")
def _discard_rolled_back_authoring_cache(session: Session, previous_transaction) -> None:
    # A rolled-back formula/symbol ID can be reused by the next transaction.
    for key in (
        "_proof_prior_cache",
        "_formula_tokens_pure_cache",
        "_formula_tokens_cache",
        "_formula_hash_cache",
        "_symbol_meta_cache",
        "_symbol_public_id_cache",
        "_formula_type_cache",
        "_namespace_cache",
    ):
        session.info.pop(key, None)
    session.info["_proof_cache_epoch"] = object()


@event.listens_for(Session, "after_flush")
def _discard_edited_proof_prefixes(session: Session, flush_context) -> None:
    # Appending new rows is handled incrementally. Edits/deletes to existing
    # source rows must not leave a previously validated prefix in the cache.
    sources = (ProofStep, ProofStepArg, ProofStepSubstTerm, ProofStepSubstProp,
               ProofStepSubstPropParam, TheoremPremise, Proof)
    if any(isinstance(row, sources) for row in (*session.dirty, *session.deleted)):
        session.info.pop("_proof_prior_cache", None)
        session.info["_proof_cache_epoch"] = object()


class ProofService:
    def __init__(
        self,
        session: Session,
        *,
        authoring_via: AuthoringVia | None = None,
    ) -> None:
        self._session = session
        self._inference_rule_name_cache: dict[str, InferenceRule] = {}
        self._symbol_cache: dict[int, Symbol] = {}
        self._theorem_premise_cache: dict[int, list[TheoremPremise]] = {}
        self._used_axioms_cache: dict[int, tuple[Axiom, ...]] = {}
        # Kept in step with `_used_axioms_cache`: the same answer as ids,
        # which is what the shared traversal consumes and produces.
        self._used_axiom_ids_cache: dict[int, frozenset[int]] = {}
        self._authoring_scope = None
        self._authoring_via = authoring_via

    def get_inference_rule(self, id: int) -> InferenceRule:
        row = self._session.get(InferenceRule, id)
        if row is None:
            raise NotFoundError("InferenceRule", id)
        return row

    def get_inference_rule_by_name(self, name: str) -> InferenceRule:
        cached = self._inference_rule_name_cache.get(name)
        if cached is not None:
            return cached
        row = self._session.scalar(select(InferenceRule).where(InferenceRule.name == name))
        if row is None:
            raise NotFoundError("InferenceRule", name)
        self._inference_rule_name_cache[name] = row
        return row

    def list_inference_rules(self) -> list[InferenceRule]:
        return list(self._session.scalars(select(InferenceRule).order_by(InferenceRule.id)))

    def create_proof(
        self,
        theorem_id: int,
        name: str | None = None,
        remarks: str | None = None,
    ) -> Proof:
        theorem = self._session.get(Theorem, theorem_id)
        if theorem is None:
            raise NotFoundError("Theorem", theorem_id)
        sequence = self._session.get(ProofIdentitySequence, theorem_id)
        if sequence is None:
            sequence = ProofIdentitySequence(theorem_id=theorem_id, next_ordinal=0)
            self._session.add(sequence)
            self._session.flush()
        ordinal = sequence.next_ordinal
        sequence.next_ordinal += 1
        proof = Proof(
            public_id=deterministic_public_id(
                "proof", f"{theorem.public_id}::{ordinal}"
            ),
            theorem_id=theorem_id,
            identity_ordinal=ordinal,
            name=name,
            status="draft",
            remarks=remarks,
        )
        self._session.add(proof)
        self._session.flush()
        record_authoring_provenance(
            self._session,
            entity_kind="proof",
            entity_id=proof.id,
            via=self._authoring_via,
        )
        return proof

    def get(self, id: int) -> Proof:
        row = self._session.get(Proof, id)
        if row is None:
            raise NotFoundError("Proof", id)
        return row

    def get_by_public_id(self, public_id: str) -> Proof:
        row = self._session.scalar(select(Proof).where(Proof.public_id == public_id))
        if row is None:
            raise NotFoundError("Proof", public_id)
        return row

    def list_for_theorem(self, theorem_id: int) -> list[Proof]:
        theorem = self._session.get(Theorem, theorem_id)
        if theorem is None:
            raise NotFoundError("Theorem", theorem_id)
        return list(
            self._session.scalars(
                select(Proof).where(Proof.theorem_id == theorem_id).order_by(Proof.id)
            )
        )

    def _matched_token_maps(
        self,
        matched: MatchResult,
        symbol_meta: dict[int, SymbolMeta],
    ) -> tuple[
        dict[int, tuple[list[Token], tuple[int, ...]]],
        dict[int, list[Token]],
        set[int],
    ]:
        """Materialize first-order/Miller matches with one shared formal choice."""
        term_map = {
            source_id: list(tokens)
            for source_id, tokens in matched.term_substs.items()
        }
        prop_map: dict[int, tuple[list[Token], tuple[int, ...]]] = {}
        failed: set[int] = set()
        needs_formal = any(
            symbol_meta[source_id].arity > 0 for source_id in matched.prop_substs
        )
        formal_symbol = None
        if needs_formal:
            occupied = {
                token.symbol_id
                for binding in matched.prop_substs.values()
                for token in binding.body_tokens
                if token.symbol_id is not None
            }
            formal_symbol = self._session.scalar(
                select(Symbol)
                .join(SymbolType, Symbol.symbol_type_id == SymbolType.id)
                .where(
                    SymbolType.name == SymbolTypeName.FREE_TERM_VAR.value,
                    Symbol.id.not_in(occupied),
                )
                .order_by(Symbol.id)
            )
            if formal_symbol is not None:
                symbol_meta[formal_symbol.id] = FormulaService(
                    self._session
                )._symbol_to_meta(formal_symbol)

        for source_id, binding in matched.prop_substs.items():
            try:
                if symbol_meta[source_id].arity == 0:
                    prop_map[source_id] = (list(binding.body_tokens), ())
                else:
                    if formal_symbol is None:
                        raise ValueError("no term variable is available")
                    prop_map[source_id] = (
                        _materialize_miller_body(
                            binding, formal_symbol.id, symbol_meta
                        ),
                        (formal_symbol.id,),
                    )
            except (KeyError, ValueError, ValidationError):
                failed.add(source_id)
        return prop_map, term_map, failed

    def suggest_step(
        self,
        proof_id: int,
        *,
        kind: str,
        applied_theorem_id: int | None = None,
        axiom_id: int | None = None,
        arg_step_ords: Sequence[int] = (),
        goal_tokens: list[Token] | None = None,
    ) -> dict[str, object]:
        """Infer substitutions and premise arguments for an axiom/theorem step.

        This authoring command interns inferred substitution bodies because the
        persisted substitution contract identifies formulas by id. Calling it
        may therefore add formula rows, although interning is idempotent. Keep
        the HTTP endpoint out of read-only deployment allowlists.
        """
        self.get(proof_id)
        if kind == "theorem":
            if applied_theorem_id is None:
                raise ValidationError("theorem suggestion requires applied_theorem_id")
            theorem = TheoremService(self._session).get(applied_theorem_id)
            applied_proof = self._session.scalar(
                select(Proof)
                .where(Proof.theorem_id == theorem.id, Proof.status == "verified")
                .order_by(Proof.id)
            )
            if applied_proof is None:
                raise ValidationError(
                    "applied theorem has no verified proof", code="proof.unverified_citation"
                )
            premise_patterns = [
                self._tokens_for_formula(row.formula_id)
                for row in self._theorem_premise_rows(theorem.id)
            ]
            conclusion_pattern = self._tokens_for_formula(theorem.conclusion_formula_id)
            applied_proof_id: int | None = applied_proof.id
        elif kind == "axiom":
            if axiom_id is None:
                raise ValidationError("axiom suggestion requires axiom_id")
            axiom = self._get_axiom(axiom_id)
            premise_patterns = []
            conclusion_pattern = self._tokens_for_formula(axiom.formula_id)
            applied_proof_id = None
        else:
            raise ValidationError("suggestion kind must be 'axiom' or 'theorem'")

        if len(arg_step_ords) > len(premise_patterns):
            raise ValidationError("too many argument steps for applied theorem")
        prior_steps = list(
            self._session.scalars(
                select(ProofStep).where(ProofStep.proof_id == proof_id).order_by(ProofStep.ord)
            )
        )
        prior_tokens = {
            step.ord: self._tokens_for_formula(step.conclusion_formula_id)
            for step in prior_steps
        }
        patterns = [*premise_patterns, conclusion_pattern]
        all_tokens = [token for formula in patterns for token in formula]
        all_tokens.extend(token for formula in prior_tokens.values() for token in formula)
        if goal_tokens:
            FormulaService(self._session).validate(goal_tokens)
            all_tokens.extend(goal_tokens)
        symbol_meta = self._symbol_meta_for_tokens(all_tokens)
        matched = MatchResult()
        argument_tokens: list[list[Token]] = []
        for premise, step_ord in zip(premise_patterns, arg_step_ords):
            if step_ord not in prior_tokens:
                raise ValidationError("arg_step_ord must reference an existing step")
            argument_tokens.append(prior_tokens[step_ord])
        if match_theorem_constraints(
            premise_patterns,
            conclusion_pattern,
            argument_tokens,
            goal_tokens,
            symbol_meta,
            matched,
        ) is None:
            raise ValidationError(
                "selected arguments or goal do not match",
                code="proof.suggestion_no_match",
            )

        schema_ids = {
            token.symbol_id
            for formula in patterns
            for token in formula
            if token.symbol_id is not None
            and symbol_meta[token.symbol_id].symbol_type_name
            in {SymbolTypeName.FREE_TERM_VAR, SymbolTypeName.FREE_PROP_VAR}
        }
        formula_service = FormulaService(
            self._session,
            authoring_via=self._authoring_via if self._authoring_via == "manual" else None,
        )
        prop_map, term_map, failed_matches = self._matched_token_maps(
            matched, symbol_meta
        )
        term_items: list[TermSubst] = []
        for source_id, target in term_map.items():
            formula = formula_service.register(target)
            term_items.append(TermSubst(source_id, formula.id))

        prop_items: list[PropSubst] = []
        undetermined: list[dict[str, object]] = []
        undetermined_ids: set[int] = set(matched.undetermined) | failed_matches
        reported_undetermined_ids = failed_matches | (
            set(matched.undetermined) - matched.prop_substs.keys()
        )
        for source_id, (body, params) in list(prop_map.items()):
            try:
                formula = formula_service.register(body)
            except (ValueError, ValidationError):
                undetermined_ids.add(source_id)
                reported_undetermined_ids.add(source_id)
                prop_map.pop(source_id)
                continue
            prop_items.append(PropSubst(source_id, formula.id, params))

        for source_id in sorted(reported_undetermined_ids):
            undetermined.append(
                {"symbol_id": source_id, "name": self._get_symbol(source_id).name,
                 "reason": "higher_order_pattern"}
            )
        determined = (
            set(matched.term_substs) | set(matched.prop_substs) | undetermined_ids
        )
        defaulted = sorted(schema_ids - determined)

        conclusion_tokens = apply_substitution_pure(
            conclusion_pattern, prop_map, term_map, symbol_meta
        )
        instantiated_premises = [
            apply_substitution_pure(item, prop_map, term_map, symbol_meta)
            for item in premise_patterns
        ]
        arg_candidates = [
            [ord_ for ord_, tokens in prior_tokens.items() if tokens == premise]
            for premise in instantiated_premises
        ]
        return {
            "applied_proof_id": applied_proof_id,
            "subst": Substitution(tuple(prop_items), tuple(term_items)),
            "undetermined": undetermined,
            "defaulted_to_identity": defaulted,
            "conclusion_tokens": conclusion_tokens,
            "premise_count": len(premise_patterns),
            "arg_candidates": arg_candidates,
        }

    def suggest_backward_steps(
        self,
        proof_id: int,
        *,
        kind: str,
        goal_tokens: list[Token],
        subst: Substitution = Substitution(),
        applied_theorem_id: int | None = None,
        axiom_id: int | None = None,
        max_depth: int = 3,
    ) -> list[BackwardStepSuggestion]:
        """Suggest an axiom/theorem application followed by bounded MP steps.

        This is the public matching boundary used by HTTP authoring.  Like
        :meth:`suggest_step`, it may intern formulas for inferred substitution
        bodies and therefore is an authoring command rather than a read.
        """
        if max_depth < 0 or max_depth > 3:
            raise ValidationError("backward suggestion depth must be between 0 and 3")
        self.get(proof_id)
        FormulaService(self._session).validate(goal_tokens)
        self._validate_substitution(subst)

        if kind == "axiom":
            if axiom_id is None:
                raise ValidationError("axiom suggestion requires axiom_id")
            conclusion_formula_id = self._get_axiom(axiom_id).formula_id
            premise_formula_ids: list[int] = []
        elif kind == "theorem":
            if applied_theorem_id is None:
                raise ValidationError("theorem suggestion requires applied_theorem_id")
            theorem = TheoremService(self._session).get(applied_theorem_id)
            conclusion_formula_id = theorem.conclusion_formula_id
            premise_formula_ids = [
                row.formula_id for row in self._theorem_premise_rows(theorem.id)
            ]
        else:
            raise ValidationError("suggestion kind must be 'axiom' or 'theorem'")

        conclusion_pattern = self._tokens_for_formula(conclusion_formula_id)
        premise_patterns = [
            self._tokens_for_formula(formula_id)
            for formula_id in premise_formula_ids
        ]
        override_prop, override_term = self._subst_to_token_maps(subst)
        implication = SymbolService(self._session).get_by_role("implication")
        all_tokens = [
            *conclusion_pattern,
            *goal_tokens,
            *[token for pattern in premise_patterns for token in pattern],
            *term_subst_tokens(override_term),
            *prop_subst_tokens(override_prop),
            Token(symbol_id=implication.id),
        ]
        symbol_meta = self._symbol_meta_for_tokens(all_tokens)
        schema_ids = {
            token.symbol_id
            for pattern in [*premise_patterns, conclusion_pattern]
            for token in pattern
            if token.symbol_id is not None
            and symbol_meta[token.symbol_id].symbol_type_name
            in {SymbolTypeName.FREE_TERM_VAR, SymbolTypeName.FREE_PROP_VAR}
        }
        override_ids = {
            item.source_symbol_id
            for item in [*subst.term_substs, *subst.prop_substs]
        }
        overridden_conclusion = apply_substitution_pure(
            conclusion_pattern, override_prop, override_term, symbol_meta
        )

        candidates: list[BackwardStepSuggestion] = []
        seen_recipes: set[tuple[object, ...]] = set()
        remainder = overridden_conclusion
        for match_depth in range(max_depth + 1):
            matched = MatchResult()
            if match_theorem_constraints(
                [], remainder, [], goal_tokens, symbol_meta, matched
            ) is not None:
                inferred_prop, inferred_term, _ = self._matched_token_maps(
                    matched, symbol_meta
                )
                full_goal = apply_substitution_pure(
                    overridden_conclusion,
                    inferred_prop,
                    inferred_term,
                    symbol_meta,
                )
                suggestion = self.suggest_step(
                    proof_id,
                    kind=kind,
                    applied_theorem_id=applied_theorem_id,
                    axiom_id=axiom_id,
                    goal_tokens=full_goal,
                )
                concrete = suggestion["conclusion_tokens"]
                antecedent_goals: list[list[Token]] = []
                intermediate_conclusions: list[list[Token]] = []
                for _ in range(match_depth):
                    antecedent, concrete = decompose_implication_pure(
                        concrete, implication.id, symbol_meta
                    )
                    antecedent_goals.append(antecedent)
                    intermediate_conclusions.append(concrete)

                undetermined_ids = set(matched.undetermined)
                determined_ids = (
                    set(matched.term_substs)
                    | set(matched.prop_substs)
                    | undetermined_ids
                    | override_ids
                )
                defaulted = sorted(schema_ids - determined_ids)
                suggested_subst = suggestion["subst"]
                prop_items = {
                    item.source_symbol_id: item
                    for item in suggested_subst.prop_substs
                }
                prop_items.update(
                    {item.source_symbol_id: item for item in subst.prop_substs}
                )
                term_items = {
                    item.source_symbol_id: item
                    for item in suggested_subst.term_substs
                }
                term_items.update(
                    {item.source_symbol_id: item for item in subst.term_substs}
                )
                concrete_subst = Substitution(
                    prop_substs=tuple(
                        item
                        for _, item in sorted(prop_items.items())
                        if item.source_symbol_id not in defaulted
                    ),
                    term_substs=tuple(
                        item
                        for _, item in sorted(term_items.items())
                        if item.source_symbol_id not in defaulted
                    ),
                )
                undetermined = list(suggestion["undetermined"])
                reported_undetermined = {
                    item["symbol_id"] for item in undetermined
                }
                for source_id in sorted(
                    undetermined_ids - reported_undetermined
                ):
                    undetermined.append(
                        {
                            "symbol_id": source_id,
                            "name": self._get_symbol(source_id).name,
                            "reason": "higher_order_pattern",
                        }
                    )
                premise_goals = [
                    self.compute_substituted_tokens(formula_id, concrete_subst)
                    for formula_id in premise_formula_ids
                ]
                prior_tokens = {
                    step.ord: self._tokens_for_formula(step.conclusion_formula_id)
                    for step in self.list_steps(proof_id)
                }
                arg_candidates = [
                    [
                        ord_
                        for ord_, tokens in prior_tokens.items()
                        if tokens == premise
                    ]
                    for premise in premise_goals
                ]
                recipe_key = (
                    tuple(suggestion["conclusion_tokens"]),
                    tuple(tuple(tokens) for tokens in antecedent_goals),
                    tuple(tuple(tokens) for tokens in premise_goals),
                )
                if recipe_key not in seen_recipes:
                    seen_recipes.add(recipe_key)
                    candidates.append(
                        BackwardStepSuggestion(
                            match_depth=match_depth,
                            applied_proof_id=suggestion["applied_proof_id"],
                            subst=concrete_subst,
                            undetermined=undetermined,
                            defaulted_to_identity=defaulted,
                            application_conclusion_tokens=suggestion[
                                "conclusion_tokens"
                            ],
                            antecedent_goals=antecedent_goals,
                            intermediate_conclusions=intermediate_conclusions,
                            premise_count=suggestion["premise_count"],
                            premise_goals=premise_goals,
                            arg_candidates=arg_candidates,
                        )
                    )
            if match_depth == max_depth:
                break
            try:
                _, remainder = decompose_implication_pure(
                    remainder, implication.id, symbol_meta
                )
            except ProofValidationError:
                break
        return candidates

    def add_step(
        self,
        proof_id: int,
        step_input: ProofStepInput,
        conclusion_formula_id: int | None = None,
    ) -> ProofStep:
        proof = self.get(proof_id)
        if proof.status != "draft":
            raise ValidationError("cannot add steps to a non-draft proof")
        scope = (self._session.get_nested_transaction() or self._session.get_transaction(),
                 self._session.info.get("_proof_cache_epoch"))
        if scope != self._authoring_scope:
            self._symbol_cache.clear()
            self._theorem_premise_cache.clear()
            self._inference_rule_name_cache.clear()
            self._authoring_scope = scope
        if isinstance(step_input, AssumptionStepInput) and conclusion_formula_id is None:
            raise ValidationError(
                "assumption step requires a conclusion",
                code="proof.assumption_needs_conclusion",
            )
        # A temporary proposition is needed to construct StepData. For every
        # derivable step its tokens are ignored by validate_proof_step and are
        # replaced with the derived, interned formula before persistence.
        placeholder_id = conclusion_formula_id or proof.theorem.conclusion_formula_id
        conclusion = self._get_proposition_formula(
            placeholder_id, "conclusion must be a proposition"
        )
        ord_ = self._next_step_ord(proof_id)

        if isinstance(step_input, PremiseStepInput):
            self._validate_premise_ord(proof.theorem_id, step_input.premise_ord)
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="premise",
                conclusion_formula_id=conclusion.id,
                premise_ord=step_input.premise_ord,
            )
            arg_ords: tuple[int, ...] = ()
            subst = Substitution()
        elif isinstance(step_input, AssumptionStepInput):
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="assumption",
                conclusion_formula_id=conclusion.id,
            )
            arg_ords = ()
            subst = Substitution()
        elif isinstance(step_input, AxiomStepInput):
            self._get_axiom(step_input.axiom_id)
            self._validate_substitution(step_input.subst)
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="axiom",
                conclusion_formula_id=conclusion.id,
                axiom_id=step_input.axiom_id,
            )
            arg_ords = ()
            subst = step_input.subst
        elif isinstance(step_input, TheoremStepInput):
            applied_proof = self.get(step_input.applied_proof_id)
            expected_arg_count = len(self._theorem_premise_rows(applied_proof.theorem_id))
            if len(step_input.arg_step_ords) != expected_arg_count:
                raise ValidationError("theorem step arg count must match applied theorem premises")
            self._validate_substitution(step_input.subst)
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="theorem",
                conclusion_formula_id=conclusion.id,
                applied_proof_id=step_input.applied_proof_id,
            )
            arg_ords = step_input.arg_step_ords
            subst = step_input.subst
        elif isinstance(step_input, MPStepInput):
            rule = self.get_inference_rule_by_name("MP")
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="rule",
                conclusion_formula_id=conclusion.id,
                inference_rule_id=rule.id,
            )
            arg_ords = (step_input.antecedent_step_ord, step_input.implication_step_ord)
            subst = Substitution()
        elif isinstance(step_input, GenStepInput):
            rule = self.get_inference_rule_by_name("Gen")
            self._validate_term_free_symbol(step_input.gen_variable_symbol_id, "gen_variable must be a term-free-variable symbol")
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="rule",
                conclusion_formula_id=conclusion.id,
                inference_rule_id=rule.id,
                gen_variable_symbol_id=step_input.gen_variable_symbol_id,
            )
            arg_ords = (step_input.body_step_ord,)
            subst = Substitution()
        elif isinstance(step_input, ImplicationIntroStepInput):
            rule = self.get_inference_rule_by_name("ImpIntro")
            step = ProofStep(
                proof_id=proof_id,
                ord=ord_,
                step_kind="rule",
                conclusion_formula_id=conclusion.id,
                inference_rule_id=rule.id,
            )
            arg_ords = (step_input.assumption_step_ord, step_input.body_step_ord)
            subst = Substitution()
        else:
            raise TypeError(f"unsupported proof step input: {type(step_input)!r}")

        for referenced_ord in arg_ords:
            self._validate_prior_step(proof_id, ord_, referenced_ord)

        prefix = self._prior_judgements(proof, ord_)
        prop_subst, term_subst = self._subst_to_token_maps(subst)
        data = self._build_step_data(
            step, arg_step_ords=list(arg_ords), prop_subst=prop_subst, term_subst=term_subst,
        )
        prefix.symbol_meta.update(self._symbol_meta_for_step_data([], [], [data]))
        derived = self._derive_step_conclusion(data, prefix)
        if conclusion_formula_id is None:
            conclusion = FormulaService(
                self._session,
                authoring_via=self._authoring_via if self._authoring_via == "manual" else None,
            ).register(derived.tokens)
            step.conclusion_formula_id = conclusion.id
        elif not isinstance(step_input, AssumptionStepInput) and derived.tokens != data.conclusion_tokens:
            raise ProofValidationError(
                "step conclusion mismatch", ord_, code="proof.step_conclusion_mismatch",
                details=_mismatch_details(derived.tokens, data.conclusion_tokens, prefix.symbol_meta),
            )

        self._session.add(step)
        if self._authoring_via == "manual":
            record_authoring_provenance(
                self._session,
                entity_kind="proof_step",
                entity_id=f"{proof_id}:{ord_}",
                via=self._authoring_via,
            )
        self._insert_args(proof_id, ord_, arg_ords)
        self._insert_substitution(proof_id, ord_, subst)
        self._session.flush()
        prefix.prior[ord_] = derived
        if isinstance(step_input, AssumptionStepInput):
            prefix.assumptions[ord_] = derived.tokens
        prefix.next_ord = ord_ + 1
        return step

    def _derive_step_conclusion(self, data: StepData, prefix: _ProofPrefix) -> StepJudgement:
        try:
            return validate_proof_step(
                step=data, prior=prefix.prior, premise_tokens_list=prefix.premises,
                symbol_meta=prefix.symbol_meta, implication_symbol_id=prefix.implication_id,
                forall_symbol_id=prefix.forall_id, assumption_tokens=prefix.assumptions,
            )
        except ProofValidationError as exc:
            if exc.step_ord is None:
                exc.step_ord = data.ord
            raise

    def _prior_judgements(self, proof: Proof, next_ord: int) -> _ProofPrefix:
        scope = self._session.get_nested_transaction() or self._session.get_transaction()
        cached_scope, cache = self._session.info.get("_proof_prior_cache", (None, {}))
        if cached_scope is not scope:
            cache = {}
        self._session.info["_proof_prior_cache"] = (scope, cache)
        prefix = cache.get(proof.id)
        if prefix is not None and prefix.next_ord == next_ord:
            return prefix

        # A fresh request (or a bulk append) replays the existing prefix once.
        premises = [self._tokens_for_formula(row.formula_id)
                    for row in self._theorem_premise_rows(proof.theorem_id)]
        data = []
        if next_ord:
            steps = self.list_steps(proof.id)
            args, props, terms = self._prefetch_step_relations(proof.id)
            data = [self._build_step_data(
                step, arg_step_ords=args.get(step.ord, []),
                prop_subst=props.get(step.ord, {}), term_subst=terms.get(step.ord, {}),
            ) for step in steps]
        symbols = SymbolService(self._session)
        prefix = _ProofPrefix(
            next_ord, {}, {}, premises, self._symbol_meta_for_step_data([], premises, data),
            symbols.get_by_role("implication").id, symbols.get_by_role("universal_quantifier").id,
        )
        for step in data:
            judgement = self._derive_step_conclusion(step, prefix)
            if judgement.tokens != step.conclusion_tokens:
                raise ProofValidationError(
                    "step conclusion mismatch", step.ord, code="proof.step_conclusion_mismatch",
                    details=_mismatch_details(judgement.tokens, step.conclusion_tokens, prefix.symbol_meta),
                )
            prefix.prior[step.ord] = judgement
            if step.step_kind == _ASSUMPTION:
                prefix.assumptions[step.ord] = judgement.tokens
        cache[proof.id] = prefix
        return prefix

    def add_raw_steps(
        self,
        proof_id: int,
        steps: Sequence[tuple[ProofStepInput, int]],
    ) -> list[ProofStep]:
        """Batch-persist ordinary raw proof steps for seed generators.

        The interactive ``add_step`` API retains its per-step validation and
        flush behavior.  This seed-only path accepts just premise, assumption,
        axiom, theorem, MP, Gen, and ⇒intro inputs, validates their static
        references, writes one unit of work, and leaves the full semantic check
        to ``validate``.
        """
        proof = self.get(proof_id)
        if proof.status != "draft":
            raise ValidationError("cannot add steps to a non-draft proof")
        if not steps:
            return []

        start_ord = self._next_step_ord(proof_id)
        available_ords = set(
            self._session.scalars(
                select(ProofStep.ord).where(ProofStep.proof_id == proof_id)
            )
        )
        rows: list[ProofStep] = []
        relations: list[tuple[int, tuple[int, ...], Substitution]] = []
        mp_rule: InferenceRule | None = None
        gen_rule: InferenceRule | None = None
        imp_intro_rule: InferenceRule | None = None

        with self._session.no_autoflush:
            for offset, (step_input, conclusion_formula_id) in enumerate(steps):
                ord_ = start_ord + offset
                conclusion = self._get_proposition_formula(
                    conclusion_formula_id, "conclusion must be a proposition"
                )

                if isinstance(step_input, PremiseStepInput):
                    self._validate_premise_ord(
                        proof.theorem_id, step_input.premise_ord
                    )
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="premise",
                        conclusion_formula_id=conclusion.id,
                        premise_ord=step_input.premise_ord,
                    )
                    arg_ords: tuple[int, ...] = ()
                    subst = Substitution()
                elif isinstance(step_input, AssumptionStepInput):
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="assumption",
                        conclusion_formula_id=conclusion.id,
                    )
                    arg_ords = ()
                    subst = Substitution()
                elif isinstance(step_input, AxiomStepInput):
                    self._get_axiom(step_input.axiom_id)
                    self._validate_substitution(step_input.subst)
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="axiom",
                        conclusion_formula_id=conclusion.id,
                        axiom_id=step_input.axiom_id,
                    )
                    arg_ords = ()
                    subst = step_input.subst
                elif isinstance(step_input, TheoremStepInput):
                    applied_proof = self.get(step_input.applied_proof_id)
                    expected_arg_count = len(
                        self._theorem_premise_rows(applied_proof.theorem_id)
                    )
                    if len(step_input.arg_step_ords) != expected_arg_count:
                        raise ValidationError(
                            "theorem step arg count must match applied theorem premises"
                        )
                    self._validate_substitution(step_input.subst)
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="theorem",
                        conclusion_formula_id=conclusion.id,
                        applied_proof_id=step_input.applied_proof_id,
                    )
                    arg_ords = step_input.arg_step_ords
                    subst = step_input.subst
                elif isinstance(step_input, MPStepInput):
                    if mp_rule is None:
                        mp_rule = self.get_inference_rule_by_name("MP")
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="rule",
                        conclusion_formula_id=conclusion.id,
                        inference_rule_id=mp_rule.id,
                    )
                    arg_ords = (
                        step_input.antecedent_step_ord,
                        step_input.implication_step_ord,
                    )
                    subst = Substitution()
                elif isinstance(step_input, GenStepInput):
                    if gen_rule is None:
                        gen_rule = self.get_inference_rule_by_name("Gen")
                    self._validate_term_free_symbol(
                        step_input.gen_variable_symbol_id,
                        "gen_variable must be a term-free-variable symbol",
                    )
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="rule",
                        conclusion_formula_id=conclusion.id,
                        inference_rule_id=gen_rule.id,
                        gen_variable_symbol_id=step_input.gen_variable_symbol_id,
                    )
                    arg_ords = (step_input.body_step_ord,)
                    subst = Substitution()
                elif isinstance(step_input, ImplicationIntroStepInput):
                    if imp_intro_rule is None:
                        imp_intro_rule = self.get_inference_rule_by_name("ImpIntro")
                    row = ProofStep(
                        proof_id=proof_id,
                        ord=ord_,
                        step_kind="rule",
                        conclusion_formula_id=conclusion.id,
                        inference_rule_id=imp_intro_rule.id,
                    )
                    arg_ords = (
                        step_input.assumption_step_ord,
                        step_input.body_step_ord,
                    )
                    subst = Substitution()
                else:
                    raise TypeError(
                        "add_raw_steps supports only ordinary raw proof inputs; "
                        f"got {type(step_input)!r}"
                    )

                for referenced_ord in arg_ords:
                    if referenced_ord not in available_ords:
                        raise ValidationError(
                            "arg_step_ord must reference a prior step"
                        )

                rows.append(row)
                relations.append((ord_, arg_ords, subst))
                available_ords.add(ord_)

        for row, (ord_, arg_ords, subst) in zip(rows, relations, strict=True):
            self._session.add(row)
            self._insert_args(proof_id, ord_, arg_ords)
            self._insert_substitution(proof_id, ord_, subst)
        self._session.flush()
        return rows

    def reconstruct_steps(
        self, proof_id: int
    ) -> list[tuple[ProofStepInput, list[Token]]]:
        """A stored proof, back as the `ProofStepSpec` list that built it.

        Nothing is lost in storage: `proof_step_arg` keeps the references and
        `proof_step_subst_{term,prop,prop_param}` keep the substitution, so a
        proof can be replayed, curried or inlined long after the process that
        wrote it exited.  §9.11 of the trust-boundary design turns on this --
        without it, `_ks_lift` could only discharge derivations whose cited
        theorems the caller happened to be holding in memory, which is what
        rule 12 was working around.

        Recognizer steps have no persisted payload and are refused: they are
        not discharge-safe anyway.
        """
        steps = self.list_steps(proof_id)
        args: dict[int, list[int]] = {}
        for row in self._session.scalars(
            select(ProofStepArg)
            .where(ProofStepArg.proof_id == proof_id)
            .order_by(ProofStepArg.step_ord, ProofStepArg.arg_ord)
        ):
            args.setdefault(row.step_ord, []).append(row.referenced_step_ord)

        term_substs: dict[int, list[TermSubst]] = {}
        for row in self._session.scalars(
            select(ProofStepSubstTerm)
            .where(ProofStepSubstTerm.proof_id == proof_id)
            .order_by(ProofStepSubstTerm.step_ord, ProofStepSubstTerm.source_symbol_id)
        ):
            term_substs.setdefault(row.step_ord, []).append(
                TermSubst(row.source_symbol_id, row.target_formula_id)
            )

        prop_params: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for row in self._session.scalars(
            select(ProofStepSubstPropParam)
            .where(ProofStepSubstPropParam.proof_id == proof_id)
            .order_by(ProofStepSubstPropParam.ord)
        ):
            prop_params.setdefault((row.step_ord, row.source_symbol_id), []).append(
                (row.ord, row.formal_param_symbol_id)
            )

        prop_substs: dict[int, list[PropSubst]] = {}
        for row in self._session.scalars(
            select(ProofStepSubstProp)
            .where(ProofStepSubstProp.proof_id == proof_id)
            .order_by(ProofStepSubstProp.step_ord, ProofStepSubstProp.source_symbol_id)
        ):
            params = prop_params.get((row.step_ord, row.source_symbol_id), [])
            prop_substs.setdefault(row.step_ord, []).append(
                PropSubst(
                    row.source_symbol_id,
                    row.body_formula_id,
                    tuple(symbol for _, symbol in sorted(params)),
                )
            )

        specs: list[tuple[ProofStepInput, list[Token]]] = []
        for step in steps:
            subst = Substitution(
                prop_substs=tuple(prop_substs.get(step.ord, ())),
                term_substs=tuple(term_substs.get(step.ord, ())),
            )
            referenced = args.get(step.ord, [])
            if step.step_kind == "premise":
                assert step.premise_ord is not None
                step_input: ProofStepInput = PremiseStepInput(step.premise_ord)
            elif step.step_kind == _ASSUMPTION:
                step_input = AssumptionStepInput()
            elif step.step_kind == "axiom":
                assert step.axiom_id is not None
                step_input = AxiomStepInput(step.axiom_id, subst)
            elif step.step_kind == "theorem":
                assert step.applied_proof_id is not None
                step_input = TheoremStepInput(
                    step.applied_proof_id, subst, tuple(referenced)
                )
            elif step.step_kind == "rule":
                rule = step.inference_rule
                assert rule is not None
                if rule.kind == "modus_ponens":
                    step_input = MPStepInput(referenced[0], referenced[1])
                elif rule.kind == "generalization":
                    assert step.gen_variable_symbol_id is not None
                    step_input = GenStepInput(referenced[0], step.gen_variable_symbol_id)
                elif rule.kind == "implication_intro":
                    step_input = ImplicationIntroStepInput(referenced[0], referenced[1])
                else:
                    raise NotImplementedError(
                        f"reconstruct_steps: {rule.kind!r} keeps no replayable payload"
                    )
            else:
                raise NotImplementedError(
                    f"reconstruct_steps: unsupported step kind {step.step_kind!r}"
                )
            specs.append(
                (step_input, self._tokens_for_formula(step.conclusion_formula_id))
            )
        return specs

    def list_steps(self, proof_id: int) -> list[ProofStep]:
        self.get(proof_id)
        return list(
            self._session.scalars(
                select(ProofStep).where(ProofStep.proof_id == proof_id).order_by(ProofStep.ord)
            )
        )

    def get_state(self, proof_id: int) -> ProofState:
        """Return the authoring state derived from a proof's validated prefix.

        Completed proofs take a summary-only path. Drafts replay through the
        existing proof kernel so this view cannot disagree with validation.
        """
        proof = self.get(proof_id)
        theorem = self._session.get(Theorem, proof.theorem_id)
        if theorem is None:
            raise NotFoundError("Theorem", proof.theorem_id)

        goal_tokens = self._tokens_for_formula(theorem.conclusion_formula_id)
        premise_tokens = [
            self._tokens_for_formula(row.formula_id)
            for row in self._theorem_premise_rows(theorem.id)
        ]
        summary_premises = [
            ProofStatePremise(ord=ord_, tokens=tokens, used_by=[])
            for ord_, tokens in enumerate(premise_tokens)
        ]
        if proof.status == "verified":
            return ProofState(
                goal_tokens=goal_tokens,
                premises=summary_premises,
                established=[],
                open_assumptions=[],
                reached_goal=True,
                blocking=[],
            )
        if proof.status == "rejected":
            return ProofState(
                goal_tokens=goal_tokens,
                premises=summary_premises,
                established=[],
                open_assumptions=[],
                reached_goal=False,
                blocking=["validation_failed"],
            )

        steps = self.list_steps(proof.id)
        next_ord = steps[-1].ord + 1 if steps else 0
        prefix = self._prior_judgements(proof, next_ord)
        assumption_ords_by_dep: dict[DepKey, list[int]] = defaultdict(list)
        for step_ord, tokens in prefix.assumptions.items():
            assumption_ords_by_dep[assumption_dep(tokens)].append(step_ord)

        used_by: dict[int, list[int]] = {
            ord_: [] for ord_ in range(len(premise_tokens))
        }
        established: list[ProofStateEstablished] = []
        for step in steps:
            judgement = prefix.prior[step.ord]
            premise_ords = sorted(
                key
                for kind, key in judgement.premise_deps
                if kind == _PREMISE and isinstance(key, int)
            )
            assumption_ords = sorted(
                step_ord
                for dependency in judgement.premise_deps
                if dependency[0] == _ASSUMPTION
                for step_ord in assumption_ords_by_dep.get(dependency, [])
            )
            for premise_ord in premise_ords:
                used_by[premise_ord].append(step.ord)
            established.append(
                ProofStateEstablished(
                    ord=step.ord,
                    tokens=judgement.tokens,
                    step_kind=step.step_kind,
                    depends_on_premises=premise_ords,
                    depends_on_assumptions=assumption_ords,
                )
            )

        final = prefix.prior[steps[-1].ord] if steps else None
        final_deps = final.premise_deps if final is not None else frozenset()
        open_assumptions = [
            ProofStateOpenAssumption(step_ord=step_ord, tokens=tokens)
            for step_ord, tokens in sorted(prefix.assumptions.items())
            if assumption_dep(tokens) in final_deps
        ]
        goal_matches = final is not None and final.tokens == goal_tokens
        reached_goal = goal_matches and not open_assumptions
        blocking: list[str] = []
        if open_assumptions:
            blocking.append("open_assumption")
        if not goal_matches:
            blocking.append("goal_not_reached")
        return ProofState(
            goal_tokens=goal_tokens,
            premises=[
                ProofStatePremise(
                    ord=ord_, tokens=tokens, used_by=used_by[ord_]
                )
                for ord_, tokens in enumerate(premise_tokens)
            ],
            established=established,
            open_assumptions=open_assumptions,
            reached_goal=reached_goal,
            blocking=blocking,
        )

    def list_step_followups(
        self, proof_id: int, step_ord: int, max_depth: int = 3
    ) -> list[ProofStepFollowup]:
        """Suggest deterministic MP eliminations rooted at one proof step."""
        if max_depth < 1 or max_depth > 3:
            raise ValidationError("followup depth must be between 1 and 3")
        proof = self.get(proof_id)
        if proof.status != "draft":
            return []
        step = self._session.get(ProofStep, (proof_id, step_ord))
        if step is None:
            raise NotFoundError("ProofStep", f"{proof_id}:{step_ord}")

        steps = self.list_steps(proof_id)
        next_ord = steps[-1].ord + 1 if steps else 0
        prefix = self._prior_judgements(proof, next_ord)
        theorem = self._session.get(Theorem, proof.theorem_id)
        if theorem is None:
            raise NotFoundError("Theorem", proof.theorem_id)
        goal_tokens = self._tokens_for_formula(theorem.conclusion_formula_id)

        # Each frontier entry is the implication-producing step (real at depth
        # zero, then the ordinal it would receive if the preceding proposal is
        # accepted), its conclusion, and its kernel dependency set.
        frontier = [(step_ord, prefix.prior[step_ord].tokens, prefix.prior[step_ord].premise_deps)]
        proposals: list[ProofStepFollowup] = []
        for depth in range(max_depth):
            following = []
            for implication_ord, implication_tokens, implication_deps in frontier:
                try:
                    antecedent_tokens, conclusion_tokens = decompose_implication_pure(
                        implication_tokens, prefix.implication_id, prefix.symbol_meta
                    )
                except ProofValidationError:
                    continue
                for antecedent_ord, antecedent in sorted(prefix.prior.items()):
                    if antecedent.tokens != antecedent_tokens:
                        continue
                    conclusion_deps = implication_deps | antecedent.premise_deps
                    reaches_goal = conclusion_tokens == goal_tokens and not any(
                        kind == _ASSUMPTION for kind, _ in conclusion_deps
                    )
                    proposals.append(
                        ProofStepFollowup(
                            kind="mp",
                            antecedent_step_ord=antecedent_ord,
                            implication_step_ord=implication_ord,
                            conclusion_tokens=conclusion_tokens,
                            reaches_goal=reaches_goal,
                        )
                    )
                    following.append(
                        (next_ord + depth, conclusion_tokens, conclusion_deps)
                    )
            frontier = following
            if not frontier:
                break
        return proposals

    def validate(self, proof_id: int) -> None:
        proof = self.get(proof_id)
        if proof.status == "verified":
            return

        try:
            theorem = self._session.get(Theorem, proof.theorem_id)
            if theorem is None:
                raise NotFoundError("Theorem", proof.theorem_id)

            goal_tokens = self._tokens_for_formula(theorem.conclusion_formula_id)
            premise_rows = self._theorem_premise_rows(theorem.id)
            premise_tokens = [self._tokens_for_formula(row.formula_id) for row in premise_rows]
            steps = self.list_steps(proof.id)
            args_by_step, prop_subst_by_step, term_subst_by_step = (
                self._prefetch_step_relations(proof.id)
            )
            step_data = [
                self._build_step_data(
                    step,
                    arg_step_ords=args_by_step.get(step.ord, []),
                    prop_subst=prop_subst_by_step.get(step.ord, {}),
                    term_subst=term_subst_by_step.get(step.ord, {}),
                )
                for step in steps
            ]
            symbol_meta = self._symbol_meta_for_step_data(goal_tokens, premise_tokens, step_data)
            implication = SymbolService(self._session).get_by_role("implication")
            universal = SymbolService(self._session).get_by_role("universal_quantifier")

            validate_proof_steps(
                goal_tokens=goal_tokens,
                premise_tokens_list=premise_tokens,
                steps_data=step_data,
                symbol_meta=symbol_meta,
                implication_symbol_id=implication.id,
                forall_symbol_id=universal.id,
            )
        except ProofValidationError:
            proof.status = "rejected"
            self._session.flush()
            raise

        proof.status = "verified"
        self._session.flush()
        TheoremService(self._session)._promote_to_proven(proof.theorem_id)

    def list_used_axioms(self, proof_id: int) -> list[Axiom]:
        """Every axiom this proof uses, following the dependency edges defined
        in dem/services/used_axioms.py (the same ones
        AxiomService.list_theorems_provable_in_system() follows in bulk)."""
        cached = self._used_axioms_cache.get(proof_id)
        if cached is not None:
            return list(cached)
        proof = self.get(proof_id)
        axiom_ids = used_axiom_ids_for_proof(
            self._session, proof_id, known=self._used_axiom_ids_cache
        )

        axioms = (
            tuple(
                self._session.scalars(
                    select(Axiom).where(Axiom.id.in_(axiom_ids)).order_by(Axiom.id)
                )
            )
            if axiom_ids
            else ()
        )
        if proof.status == "verified":
            self._used_axioms_cache[proof_id] = axioms
            self._used_axiom_ids_cache[proof_id] = axiom_ids
        return list(axioms)

    def is_valid_in_system(self, proof_id: int, axiom_system_id: int) -> bool:
        self.get(proof_id)
        system = self._session.get(AxiomSystem, axiom_system_id)
        if system is None:
            raise NotFoundError("AxiomSystem", axiom_system_id)
        used_axioms = self.list_used_axioms(proof_id)
        # Defining axioms are conservative scaffolding, not object-theory
        # assumptions. For function_desc definitions list_used_axioms()
        # already follows the existence/uniqueness proof, so the assumptions
        # that justify introducing the symbol remain part of this check.
        used_ids = {axiom.id for axiom in used_axioms if not is_defining_axiom(axiom)}
        system_ids = set(
            self._session.scalars(
                select(AxiomSystemMember.axiom_id).where(
                    AxiomSystemMember.axiom_system_id == axiom_system_id
                )
            )
        )
        return used_ids <= system_ids

    def compute_substituted_tokens(self, formula_id: int, subst: Substitution) -> list[Token]:
        self._get_formula(formula_id)
        self._validate_substitution(subst)
        formula_tokens = self._tokens_for_formula(formula_id)
        prop_subst, term_subst = self._subst_to_token_maps(subst)
        all_tokens = [*formula_tokens, *term_subst_tokens(term_subst), *prop_subst_tokens(prop_subst)]
        symbol_meta = self._symbol_meta_for_tokens(all_tokens)
        return apply_substitution_pure(formula_tokens, prop_subst, term_subst, symbol_meta)

    def compute_gen_tokens(self, body_formula_id: int, gen_variable_symbol_id: int) -> list[Token]:
        self._get_proposition_formula(body_formula_id, "body formula must be a proposition")
        self._validate_term_free_symbol(gen_variable_symbol_id, "gen_variable must be a term-free-variable symbol")
        body_tokens = self._tokens_for_formula(body_formula_id)
        universal = SymbolService(self._session).get_by_role("universal_quantifier")
        symbol_meta = self._symbol_meta_for_tokens([*body_tokens, Token(symbol_id=universal.id)])
        return abstract_and_quantify_pure(body_tokens, gen_variable_symbol_id, universal.id, symbol_meta)

    def _next_step_ord(self, proof_id: int) -> int:
        current = self._session.scalar(
            select(func.max(ProofStep.ord)).where(ProofStep.proof_id == proof_id)
        )
        return 0 if current is None else current + 1

    def _insert_args(self, proof_id: int, step_ord: int, arg_step_ords: tuple[int, ...]) -> None:
        self._session.add_all(
            ProofStepArg(
                proof_id=proof_id,
                step_ord=step_ord,
                arg_ord=arg_ord,
                referenced_step_ord=referenced_step_ord,
            )
            for arg_ord, referenced_step_ord in enumerate(arg_step_ords)
        )

    def _insert_substitution(self, proof_id: int, step_ord: int, subst: Substitution) -> None:
        self._session.add_all(
            ProofStepSubstTerm(
                proof_id=proof_id,
                step_ord=step_ord,
                source_symbol_id=item.source_symbol_id,
                target_formula_id=item.target_formula_id,
            )
            for item in subst.term_substs
        )
        for item in subst.prop_substs:
            self._session.add(
                ProofStepSubstProp(
                    proof_id=proof_id,
                    step_ord=step_ord,
                    source_symbol_id=item.source_symbol_id,
                    body_formula_id=item.body_formula_id,
                )
            )
            for ord_, formal_param_symbol_id in enumerate(item.formal_param_symbol_ids):
                self._session.add(
                    ProofStepSubstPropParam(
                        proof_id=proof_id,
                        step_ord=step_ord,
                        source_symbol_id=item.source_symbol_id,
                        ord=ord_,
                        formal_param_symbol_id=formal_param_symbol_id,
                    )
                )

    def _prefetch_step_relations(
        self, proof_id: int
    ) -> tuple[
        dict[int, list[int]],
        dict[int, dict[int, tuple[list[Token], tuple[int, ...]]]],
        dict[int, dict[int, list[Token]]],
    ]:
        args_by_step: dict[int, list[int]] = defaultdict(list)
        for row in self._session.scalars(
            select(ProofStepArg)
            .where(ProofStepArg.proof_id == proof_id)
            .order_by(ProofStepArg.step_ord, ProofStepArg.arg_ord)
        ):
            args_by_step[row.step_ord].append(row.referenced_step_ord)

        term_subst_by_step: dict[int, dict[int, list[Token]]] = defaultdict(dict)
        for row in self._session.scalars(
            select(ProofStepSubstTerm)
            .where(ProofStepSubstTerm.proof_id == proof_id)
            .order_by(ProofStepSubstTerm.step_ord, ProofStepSubstTerm.source_symbol_id)
        ):
            term_subst_by_step[row.step_ord][row.source_symbol_id] = (
                self._tokens_for_formula(row.target_formula_id)
            )

        params: dict[tuple[int, int], list[int]] = defaultdict(list)
        for row in self._session.scalars(
            select(ProofStepSubstPropParam)
            .where(ProofStepSubstPropParam.proof_id == proof_id)
            .order_by(
                ProofStepSubstPropParam.step_ord,
                ProofStepSubstPropParam.source_symbol_id,
                ProofStepSubstPropParam.ord,
            )
        ):
            params[(row.step_ord, row.source_symbol_id)].append(
                row.formal_param_symbol_id
            )

        prop_subst_by_step: dict[
            int, dict[int, tuple[list[Token], tuple[int, ...]]]
        ] = defaultdict(dict)
        for row in self._session.scalars(
            select(ProofStepSubstProp)
            .where(ProofStepSubstProp.proof_id == proof_id)
            .order_by(ProofStepSubstProp.step_ord, ProofStepSubstProp.source_symbol_id)
        ):
            prop_subst_by_step[row.step_ord][row.source_symbol_id] = (
                self._tokens_for_formula(row.body_formula_id),
                tuple(params[(row.step_ord, row.source_symbol_id)]),
            )
        return dict(args_by_step), dict(prop_subst_by_step), dict(term_subst_by_step)

    def _build_step_data(
        self,
        step: ProofStep,
        *,
        arg_step_ords: list[int],
        prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]],
        term_subst: dict[int, list[Token]],
    ) -> StepData:

        axiom_tokens = None
        if step.axiom_id is not None:
            axiom = self._get_axiom(step.axiom_id)
            axiom_tokens = self._tokens_for_formula(axiom.formula_id)

        applied_status = None
        applied_conclusion = None
        applied_premises = None
        if step.applied_proof_id is not None:
            applied_proof = self.get(step.applied_proof_id)
            applied_status = applied_proof.status
            applied_theorem = self._session.get(Theorem, applied_proof.theorem_id)
            if applied_theorem is None:
                raise NotFoundError("Theorem", applied_proof.theorem_id)
            applied_conclusion = self._tokens_for_formula(applied_theorem.conclusion_formula_id)
            applied_premises = [
                self._tokens_for_formula(row.formula_id)
                for row in self._theorem_premise_rows(applied_theorem.id)
            ]

        return StepData(
            ord=step.ord,
            step_kind=step.step_kind,
            conclusion_tokens=self._tokens_for_formula(step.conclusion_formula_id),
            premise_ord=step.premise_ord,
            axiom_tokens=axiom_tokens,
            applied_proof_status=applied_status,
            applied_theorem_conclusion_tokens=applied_conclusion,
            applied_theorem_premise_tokens_list=applied_premises,
            prop_subst=prop_subst,
            term_subst=term_subst,
            arg_step_ords=arg_step_ords,
            gen_variable_symbol_id=step.gen_variable_symbol_id,
            inference_rule_kind=(self.get_inference_rule(step.inference_rule_id).kind
                                 if step.inference_rule_id is not None else None),
        )

    def _subst_maps_for_step(
        self, proof_id: int, step_ord: int
    ) -> tuple[dict[int, tuple[list[Token], tuple[int, ...]]], dict[int, list[Token]]]:
        term_rows = self._session.scalars(
            select(ProofStepSubstTerm).where(
                ProofStepSubstTerm.proof_id == proof_id,
                ProofStepSubstTerm.step_ord == step_ord,
            ).order_by(ProofStepSubstTerm.source_symbol_id)
        ).all()
        term_subst = {
            row.source_symbol_id: self._tokens_for_formula(row.target_formula_id)
            for row in term_rows
        }

        prop_rows = self._session.scalars(
            select(ProofStepSubstProp).where(
                ProofStepSubstProp.proof_id == proof_id,
                ProofStepSubstProp.step_ord == step_ord,
            ).order_by(ProofStepSubstProp.source_symbol_id)
        ).all()
        prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]] = {}
        for row in prop_rows:
            params = tuple(
                self._session.scalars(
                    select(ProofStepSubstPropParam.formal_param_symbol_id)
                    .where(
                        ProofStepSubstPropParam.proof_id == proof_id,
                        ProofStepSubstPropParam.step_ord == step_ord,
                        ProofStepSubstPropParam.source_symbol_id == row.source_symbol_id,
                    )
                    .order_by(ProofStepSubstPropParam.ord)
                )
            )
            prop_subst[row.source_symbol_id] = (self._tokens_for_formula(row.body_formula_id), params)
        return prop_subst, term_subst

    def _subst_to_token_maps(
        self, subst: Substitution
    ) -> tuple[dict[int, tuple[list[Token], tuple[int, ...]]], dict[int, list[Token]]]:
        prop_subst = {
            item.source_symbol_id: (
                self._tokens_for_formula(item.body_formula_id),
                item.formal_param_symbol_ids,
            )
            for item in subst.prop_substs
        }
        term_subst = {
            item.source_symbol_id: self._tokens_for_formula(item.target_formula_id)
            for item in subst.term_substs
        }
        return prop_subst, term_subst

    def _validate_substitution(self, subst: Substitution) -> None:
        term_sources: set[int] = set()
        for item in subst.term_substs:
            if item.source_symbol_id in term_sources:
                raise ValidationError("duplicate term substitution source")
            term_sources.add(item.source_symbol_id)
            self._validate_term_free_symbol(item.source_symbol_id, "term substitution source must be a term-free-variable symbol")
            self._get_formula_of_type(item.target_formula_id, FormulaTypeName.TERM, "term substitution target must be a term")

        prop_sources: set[int] = set()
        for item in subst.prop_substs:
            if item.source_symbol_id in prop_sources:
                raise ValidationError("duplicate proposition substitution source")
            prop_sources.add(item.source_symbol_id)
            source = self._validate_prop_free_symbol(item.source_symbol_id)
            self._get_formula_of_type(item.body_formula_id, FormulaTypeName.PROPOSITION, "proposition substitution body must be a proposition")
            if len(item.formal_param_symbol_ids) != source.arity:
                raise ValidationError("proposition substitution formal parameter count mismatch")
            if len(set(item.formal_param_symbol_ids)) != len(item.formal_param_symbol_ids):
                raise ValidationError("proposition substitution formal parameters must be distinct")
            for param_id in item.formal_param_symbol_ids:
                self._validate_term_free_symbol(param_id, "formal parameter must be a term-free-variable symbol")

    def _validate_prior_step(self, proof_id: int, current_ord: int, referenced_ord: int) -> None:
        if referenced_ord < 0 or referenced_ord >= current_ord:
            raise ValidationError("arg_step_ord must reference a prior step")
        row = self._session.get(ProofStep, {"proof_id": proof_id, "ord": referenced_ord})
        if row is None:
            raise ValidationError("arg_step_ord must reference a prior step")

    def _validate_premise_ord(self, theorem_id: int, premise_ord: int) -> None:
        if premise_ord < 0:
            raise ValidationError("premise_ord must be >= 0")
        row = self._session.get(TheoremPremise, {"theorem_id": theorem_id, "ord": premise_ord})
        if row is None:
            raise ValidationError("premise_ord out of range")

    def _validate_term_free_symbol(self, symbol_id: int, message: str) -> Symbol:
        symbol = self._get_symbol(symbol_id)
        if symbol.symbol_type.name != SymbolTypeName.FREE_TERM_VAR.value:
            raise ValidationError(message)
        return symbol

    def _validate_prop_free_symbol(self, symbol_id: int) -> Symbol:
        symbol = self._get_symbol(symbol_id)
        if symbol.symbol_type.name != SymbolTypeName.FREE_PROP_VAR.value:
            raise ValidationError("proposition substitution source must be a proposition-free-variable symbol")
        return symbol

    def _get_symbol(self, symbol_id: int) -> Symbol:
        cached = self._symbol_cache.get(symbol_id)
        if cached is not None:
            return cached
        symbol = self._session.scalar(
            select(Symbol)
            .options(joinedload(Symbol.symbol_type))
            .where(Symbol.id == symbol_id)
        )
        if symbol is None:
            raise NotFoundError("Symbol", symbol_id)
        self._symbol_cache[symbol_id] = symbol
        return symbol

    def _get_axiom(self, axiom_id: int) -> Axiom:
        axiom = self._session.get(Axiom, axiom_id)
        if axiom is None:
            raise NotFoundError("Axiom", axiom_id)
        return axiom

    def _get_formula(self, formula_id: int) -> Formula:
        formula = self._session.get(Formula, formula_id)
        if formula is None:
            raise NotFoundError("Formula", formula_id)
        return formula

    def _get_proposition_formula(self, formula_id: int, message: str) -> Formula:
        return self._get_formula_of_type(formula_id, FormulaTypeName.PROPOSITION, message)

    def _get_formula_of_type(
        self, formula_id: int, formula_type: FormulaTypeName, message: str
    ) -> Formula:
        formula = self._get_formula(formula_id)
        if formula.formula_type.name != formula_type.value:
            raise ValidationError(message)
        return formula

    def _theorem_premise_rows(self, theorem_id: int) -> list[TheoremPremise]:
        cached = self._theorem_premise_cache.get(theorem_id)
        if cached is not None:
            return cached
        rows = list(
            self._session.scalars(
                select(TheoremPremise)
                .where(TheoremPremise.theorem_id == theorem_id)
                .order_by(TheoremPremise.ord)
            )
        )
        self._theorem_premise_cache[theorem_id] = rows
        return rows

    def _tokens_for_formula(self, formula_id: int) -> list[Token]:
        cache = self._session.info.setdefault("_formula_tokens_pure_cache", {})
        cached = cache.get(formula_id)
        if cached is not None:
            return cached
        self._get_formula(formula_id)
        rows = self._session.scalars(
            select(FormulaToken)
            .where(FormulaToken.formula_id == formula_id)
            .order_by(FormulaToken.position)
        ).all()
        tokens = [
            Token(symbol_id=row.symbol_id)
            if row.symbol_id is not None
            else Token(de_bruijn_index=row.de_bruijn_index)
            for row in rows
        ]
        cache[formula_id] = tokens
        return tokens

    def _symbol_meta_for_tokens(self, tokens: Sequence[Token]) -> dict[int, SymbolMeta]:
        return FormulaService(self._session)._load_symbol_meta(list(tokens))

    def _symbol_meta_for_step_data(
        self,
        goal_tokens: list[Token],
        premise_tokens: list[list[Token]],
        step_data: list[StepData],
    ) -> dict[int, SymbolMeta]:
        tokens: list[Token] = [*goal_tokens]
        for item in premise_tokens:
            tokens.extend(item)
        for step in step_data:
            tokens.extend(step.conclusion_tokens)
            for optional in (
                step.axiom_tokens,
                step.applied_theorem_conclusion_tokens,
            ):
                if optional is not None:
                    tokens.extend(optional)
            if step.applied_theorem_premise_tokens_list is not None:
                for premise in step.applied_theorem_premise_tokens_list:
                    tokens.extend(premise)
            if step.prop_subst is not None:
                tokens.extend(prop_subst_tokens(step.prop_subst))
                for _, params in step.prop_subst.values():
                    tokens.extend(Token(symbol_id=param) for param in params)
            if step.term_subst is not None:
                tokens.extend(term_subst_tokens(step.term_subst))
            if step.gen_variable_symbol_id is not None:
                tokens.append(Token(symbol_id=step.gen_variable_symbol_id))
        tokens.append(Token(symbol_id=SymbolService(self._session).get_by_role("universal_quantifier").id))
        tokens.append(Token(symbol_id=SymbolService(self._session).get_by_role("implication").id))
        return self._symbol_meta_for_tokens(tokens)


def term_subst_tokens(term_subst: dict[int, list[Token]]) -> list[Token]:
    tokens: list[Token] = []
    for source_id, target_tokens in term_subst.items():
        tokens.append(Token(symbol_id=source_id))
        tokens.extend(target_tokens)
    return tokens


def prop_subst_tokens(
    prop_subst: dict[int, tuple[list[Token], tuple[int, ...]]]
) -> list[Token]:
    tokens: list[Token] = []
    for source_id, (body_tokens, formal_params) in prop_subst.items():
        tokens.append(Token(symbol_id=source_id))
        tokens.extend(body_tokens)
        tokens.extend(Token(symbol_id=param_id) for param_id in formal_params)
    return tokens
