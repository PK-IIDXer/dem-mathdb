from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias


@dataclass(frozen=True)
class Token:
    """One token in a formula's polish-notation representation."""

    symbol_id: int | None = None
    de_bruijn_index: int | None = None

    def __post_init__(self) -> None:
        both_none = self.symbol_id is None and self.de_bruijn_index is None
        both_set = self.symbol_id is not None and self.de_bruijn_index is not None
        if both_none or both_set:
            raise ValueError("Token requires exactly one of symbol_id or de_bruijn_index")
        if self.symbol_id is not None and self.symbol_id <= 0:
            raise ValueError("symbol_id must be > 0")
        if self.de_bruijn_index is not None and self.de_bruijn_index < 0:
            raise ValueError("de_bruijn_index must be >= 0")

    @property
    def is_symbol(self) -> bool:
        return self.symbol_id is not None

    @property
    def is_bound_var(self) -> bool:
        return self.de_bruijn_index is not None


class FormulaTypeName(str, Enum):
    TERM = "項"
    PROPOSITION = "命題"


class SymbolTypeName(str, Enum):
    FUNCTION = "関数記号"
    PREDICATE = "述語記号"
    LOGICAL = "論理記号"
    QUANT_PROP = "命題型量化記号"
    QUANT_TERM = "項型量化記号"
    FREE_TERM_VAR = "項型自由変数記号"
    FREE_PROP_VAR = "命題型自由変数記号"


@dataclass(frozen=True)
class SymbolMeta:
    """DB-independent symbol information required by formula validation."""

    arity: int
    symbol_type_name: SymbolTypeName
    output_formula_type: FormulaTypeName
    input_formula_type: FormulaTypeName | None
    is_quantifier: bool


@dataclass(frozen=True)
class TermSubst:
    """Term substitution: source term-free variable -> target term formula."""

    source_symbol_id: int
    target_formula_id: int


@dataclass(frozen=True)
class PropSubst:
    """Proposition substitution with lambda-like formal parameters."""

    source_symbol_id: int
    body_formula_id: int
    formal_param_symbol_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Substitution:
    """A simultaneous substitution used by axiom/theorem proof steps."""

    prop_substs: tuple[PropSubst, ...] = ()
    term_substs: tuple[TermSubst, ...] = ()


@dataclass(frozen=True)
class PremiseStepInput:
    premise_ord: int


@dataclass(frozen=True)
class AxiomStepInput:
    axiom_id: int
    subst: Substitution = Substitution()


@dataclass(frozen=True)
class TheoremStepInput:
    applied_proof_id: int
    subst: Substitution = Substitution()
    arg_step_ords: tuple[int, ...] = ()


@dataclass(frozen=True)
class MPStepInput:
    antecedent_step_ord: int
    implication_step_ord: int


@dataclass(frozen=True)
class GenStepInput:
    body_step_ord: int
    gen_variable_symbol_id: int


@dataclass(frozen=True)
class AssumptionStepInput:
    """A local assumption, later discharged by `ImplicationIntroStepInput`.

    The assumed proposition is the step's own conclusion formula, so the input
    carries no data of its own. Its judgement is `{A} ⊢ A`; the kernel rejects
    any proof whose final step still depends on an undischarged assumption.
    See design doc §9.3.
    """


@dataclass(frozen=True)
class ImplicationIntroStepInput:
    """⇒introduction: from `Γ ∪ {A} ⊢ Q` conclude `Γ ⊢ A ⇒ Q`.

    `assumption_step_ord` must reference an `assumption` step; every step
    depending on that same assumed formula is discharged at once (Gentzen's
    convention), and discharging an assumption that was never used is allowed
    -- vacuous discharge is exactly `hilbert_k`.
    """

    assumption_step_ord: int
    body_step_ord: int


ProofStepInput: TypeAlias = (
    PremiseStepInput
    | AssumptionStepInput
    | AxiomStepInput
    | TheoremStepInput
    | MPStepInput
    | GenStepInput
    | ImplicationIntroStepInput
)


def rebase_step_input(
    step_input: ProofStepInput, remap: Callable[[int], int]
) -> ProofStepInput:
    """Return `step_input` with every back-reference to a prior step ordinal
    put through `remap`.

    Splicing one derivation into another means renumbering its steps, and every
    input that points backwards has to move with them. Routing all of them
    through here keeps a caller from silently copying a stale ordinal when a
    new pointing step kind appears -- which is exactly how `⇒intro` could break
    the splicers that only knew about MP.

    `PremiseStepInput` is deliberately left alone: a premise ordinal indexes the
    theorem's premise list, not the step list, so callers that re-point premises
    must handle them themselves.
    """
    if isinstance(step_input, MPStepInput):
        return MPStepInput(
            remap(step_input.antecedent_step_ord), remap(step_input.implication_step_ord)
        )
    if isinstance(step_input, GenStepInput):
        return GenStepInput(
            remap(step_input.body_step_ord), step_input.gen_variable_symbol_id
        )
    if isinstance(step_input, ImplicationIntroStepInput):
        return ImplicationIntroStepInput(
            remap(step_input.assumption_step_ord), remap(step_input.body_step_ord)
        )
    if isinstance(step_input, TheoremStepInput) and step_input.arg_step_ords:
        return TheoremStepInput(
            step_input.applied_proof_id,
            step_input.subst,
            arg_step_ords=tuple(remap(ord_) for ord_ in step_input.arg_step_ords),
        )
    return step_input


@dataclass(frozen=True)
class PredicateDefinitionInput:
    """Predicate-symbol definition: forall params. (N(params) <-> body)."""

    name: str
    param_symbol_ids: tuple[int, ...]
    body_formula_id: int
    requires_existence_proof: bool = False
    requires_uniqueness_proof: bool = False
    remarks: str | None = None
    latex_template: str | None = None


@dataclass(frozen=True)
class FunctionDefinitionInput:
    """Explicit-term function definition: forall params. N(params) = body."""

    name: str
    param_symbol_ids: tuple[int, ...]
    body_formula_id: int
    remarks: str | None = None
    latex_template: str | None = None


@dataclass(frozen=True)
class LogicalDefinitionInput:
    """Logical-symbol definition: N(prop params) <-> body."""

    name: str
    param_symbol_ids: tuple[int, ...]
    body_formula_id: int
    remarks: str | None = None
    latex_template: str | None = None


@dataclass(frozen=True)
class QuantPropDefinitionInput:
    """Proposition-quantifier definition: (N x. phi(x)) <-> body."""

    name: str
    param_symbol_id: int
    body_formula_id: int
    remarks: str | None = None
    latex_template: str | None = None


@dataclass(frozen=True)
class QuantTermDefinitionInput:
    """Term-quantifier definition: (N x. phi(x)) = body.

    The term-binder counterpart of `QuantPropDefinitionInput`: same shape, but
    the body is a *term* and the defining axiom is an equation rather than a
    biconditional. Explicit abbreviation of an already well-formed term, so --
    like `FunctionDefinitionInput` and unlike `DescriptiveFunctionDefinitionInput`
    -- it needs no existence/uniqueness proof to stay conservative. A DEM term is
    well-formed whether or not it denotes, so `N = B` claims nothing beyond
    naming `B`. See docs/design/kernel/definition.md.
    """

    name: str
    param_symbol_id: int
    body_formula_id: int
    remarks: str | None = None
    latex_template: str | None = None


@dataclass(frozen=True)
class DescriptiveFunctionDefinitionInput:
    """Descriptive (definite-description) function-symbol definition:

        forall params. forall y. (N(params) = y <-> phi(params, y))

    Conservativity is conditional on `existence_uniqueness_proof_id` proving

        forall params. exists y. (phi(params, y)
                                   and forall z. (phi(params, z) -> z = y))

    with the SAME params / value variable / body formula -- checked token-for-
    token by DefinitionService.register() at registration time. See
    docs/design/kernel/descriptive-function-definition.md.
    """

    name: str
    param_symbol_ids: tuple[int, ...]
    value_symbol_id: int
    uniqueness_witness_symbol_id: int
    body_formula_id: int
    existence_uniqueness_proof_id: int
    remarks: str | None = None
    latex_template: str | None = None


DefinitionInput: TypeAlias = (
    PredicateDefinitionInput
    | FunctionDefinitionInput
    | LogicalDefinitionInput
    | QuantPropDefinitionInput
    | QuantTermDefinitionInput
    | DescriptiveFunctionDefinitionInput
)
