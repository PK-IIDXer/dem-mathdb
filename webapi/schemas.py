from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AliasPath, BaseModel, Field, PlainSerializer, model_validator

from dem.types import Token


def _serialize_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        utc_value = value.replace(tzinfo=timezone.utc)
    else:
        utc_value = value.astimezone(timezone.utc)
    timespec = "microseconds" if utc_value.microsecond else "seconds"
    return utc_value.isoformat(timespec=timespec).replace("+00:00", "Z")


ApiDateTime = Annotated[
    datetime,
    PlainSerializer(_serialize_utc_datetime, return_type=str, when_used="json"),
]


class TokenIn(BaseModel):
    """Mirrors dem.types.Token. Exactly one of the two fields must be set."""

    symbol_id: int | None = None
    de_bruijn_index: int | None = None

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "TokenIn":
        Token(symbol_id=self.symbol_id, de_bruijn_index=self.de_bruijn_index)
        return self

    def to_domain(self) -> Token:
        return Token(symbol_id=self.symbol_id, de_bruijn_index=self.de_bruijn_index)


class TokenOut(BaseModel):
    position: int
    symbol_id: int | None
    de_bruijn_index: int | None

    model_config = {"from_attributes": True}


class FormulaTypeOut(BaseModel):
    id: int
    name: str
    code: Literal["term", "proposition"]
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class SymbolTypeOut(BaseModel):
    id: int
    name: str
    output_formula_type_id: int
    input_formula_type_id: int | None
    fixed_arity: int | None
    is_quantifier: bool
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class SymbolOut(BaseModel):
    id: int
    public_id: str
    name: str
    symbol_type_id: int
    symbol_type: SymbolTypeOut
    arity: int
    is_primitive: bool
    namespace_id: int
    namespace_name: str = Field(validation_alias=AliasPath("namespace", "name"))
    notation_kind: Literal["prefix", "infix"]
    precedence: int | None
    latex_template: str | None
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True, "populate_by_name": True}


class SymbolWithUsageOut(SymbolOut):
    usage_count: int | None = None


class SymbolAliasOut(BaseModel):
    id: int
    symbol_id: int
    alias: str
    source: Literal["builtin", "user"]

    model_config = {"from_attributes": True}


class SymbolAliasCreate(BaseModel):
    alias: str


class SymbolCreate(BaseModel):
    name: str
    symbol_type_id: int
    arity: int
    is_primitive: bool = False
    notation_kind: Literal["prefix", "infix"] = "prefix"
    precedence: int | None = None
    latex_template: str | None = None
    remarks: str | None = None


class SymbolNotationUpdate(BaseModel):
    notation_kind: Literal["prefix", "infix"]
    precedence: int | None = None


class SymbolLatexTemplateUpdate(BaseModel):
    latex_template: str | None = None


class SymbolRoleOut(BaseModel):
    role: str
    symbol_id: int
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class SymbolRoleAssign(BaseModel):
    role: str
    symbol_id: int


class TagOut(BaseModel):
    id: int
    name: str
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str


class DescriptionUpdate(BaseModel):
    description: str | None = None


class TagAttach(BaseModel):
    tag_id: int


class FormulaOut(BaseModel):
    id: int
    public_id: str
    formula_type_id: int
    formula_type: FormulaTypeOut
    hash: str
    token_count: int
    description: str | None
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class FormulaDetailOut(FormulaOut):
    tokens: list[TokenOut]


class NamedConclusionItemOut(BaseModel):
    public_id: str
    name: str
    description: str | None


class NamedConclusionsOut(BaseModel):
    axioms: list[NamedConclusionItemOut]
    theorems: list[NamedConclusionItemOut]


class FormulaValidateRequest(BaseModel):
    tokens: list[TokenIn] = Field(min_length=1)


class FormulaCreate(BaseModel):
    tokens: list[TokenIn] = Field(min_length=1)
    remarks: str | None = None


class FormulaParseRequest(BaseModel):
    text: str
    context: dict[str, int] = Field(default_factory=dict)


class FormulaParseOut(BaseModel):
    tokens: list[TokenIn]
    formula_id: int | None


class FormulaPrintRequest(BaseModel):
    tokens: list[TokenIn] = Field(min_length=1)


class FormulaPrintOut(BaseModel):
    text: str


class FormulaSearchRequest(BaseModel):
    pattern: str
    context: dict[str, int] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = Field(default=None, max_length=28)


class FormulaSearchBindingOut(BaseModel):
    kind: Literal["term", "proposition"]
    tokens: list[TokenIn]
    parameter_de_bruijn_index: int | None = None


class FormulaSearchItemOut(BaseModel):
    formula_id: int
    bindings: dict[str, FormulaSearchBindingOut]


class FormulaSearchOut(BaseModel):
    items: list[FormulaSearchItemOut]
    next_cursor: str | None


class AxiomOut(BaseModel):
    id: int
    public_id: str
    name: str
    namespace_id: int
    namespace_name: str = Field(validation_alias=AliasPath("namespace", "name"))
    formula_id: int
    formula: FormulaOut
    origin_kind: str
    definition_id: int | None
    description: str | None
    tags: list[TagOut] = Field(default_factory=list)
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class AxiomCreate(BaseModel):
    name: str
    formula_id: int
    description: str | None = None
    remarks: str | None = None


class AxiomSystemOut(BaseModel):
    id: int
    name: str
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class AxiomSystemCreate(BaseModel):
    name: str
    remarks: str | None = None


class AxiomSystemMemberAdd(BaseModel):
    axiom_id: int


class IsSubsetOut(BaseModel):
    is_subset: bool


class TheoremOut(BaseModel):
    id: int
    public_id: str
    namespace_id: int
    namespace_name: str = Field(validation_alias=AliasPath("namespace", "name"))
    name: str
    conclusion_formula_id: int
    conclusion_formula: FormulaOut
    status: str
    description: str | None
    tags: list[TagOut] = Field(default_factory=list)
    remarks: str | None
    created_at: ApiDateTime
    updated_at: ApiDateTime

    model_config = {"from_attributes": True}


class TheoremCreate(BaseModel):
    name: str
    conclusion_formula_id: int
    premise_formula_ids: list[int] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)
    description: str | None = None
    remarks: str | None = None


class TheoremPremiseOut(BaseModel):
    ord: int
    formula: FormulaOut


class TermSubstIn(BaseModel):
    source_symbol_id: int
    target_formula_id: int


class PropSubstIn(BaseModel):
    source_symbol_id: int
    body_formula_id: int
    formal_param_symbol_ids: list[int] = Field(default_factory=list)


class SubstitutionIn(BaseModel):
    prop_substs: list[PropSubstIn] = Field(default_factory=list)
    term_substs: list[TermSubstIn] = Field(default_factory=list)


class StepSuggestRequest(BaseModel):
    kind: Literal["axiom", "theorem"]
    applied_theorem_id: int | None = None
    axiom_id: int | None = None
    arg_step_ords: list[int] = Field(default_factory=list)
    goal_tokens: list[TokenIn] | None = None


class BackwardStepSuggestRequest(BaseModel):
    kind: Literal["axiom", "theorem"]
    applied_theorem_id: int | None = None
    axiom_id: int | None = None
    goal_tokens: list[TokenIn]
    subst: SubstitutionIn = Field(default_factory=SubstitutionIn)


class TermSubstOut(BaseModel):
    source_symbol_id: int
    target_formula_id: int


class PropSubstOut(BaseModel):
    source_symbol_id: int
    body_formula_id: int
    formal_param_symbol_ids: list[int]


class SubstitutionOut(BaseModel):
    prop_substs: list[PropSubstOut]
    term_substs: list[TermSubstOut]


class UndeterminedSubstitutionOut(BaseModel):
    symbol_id: int
    name: str
    reason: str


class StepSuggestOut(BaseModel):
    applied_proof_id: int | None
    subst: SubstitutionOut
    undetermined: list[UndeterminedSubstitutionOut]
    defaulted_to_identity: list[int]
    conclusion_tokens: list[TokenIn] | None
    premise_count: int
    arg_candidates: list[list[int]]


class BackwardStepSuggestionOut(BaseModel):
    match_depth: int
    applied_proof_id: int | None
    subst: SubstitutionOut
    undetermined: list[UndeterminedSubstitutionOut]
    defaulted_to_identity: list[int]
    application_conclusion_tokens: list[TokenIn]
    antecedent_goals: list[list[TokenIn]]
    intermediate_conclusions: list[list[TokenIn]]
    premise_count: int
    premise_goals: list[list[TokenIn]]
    arg_candidates: list[list[int]]


class BackwardStepSuggestOut(BaseModel):
    candidates: list[BackwardStepSuggestionOut]


class ApplicableTheoremOut(BaseModel):
    theorem: TheoremOut
    is_schematic: bool
    score: float


class InferenceRuleOut(BaseModel):
    id: int
    name: str
    kind: str
    # What justifies the rule, and -- for an admissible one -- the procedure
    # that eliminates it. Exposed because a reader deciding how much to trust a
    # proof needs it: see design doc §9.5.
    tier: str
    elimination_procedure: str | None
    premise_count: int
    requires_variable_param: bool
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class ProofOut(BaseModel):
    id: int
    public_id: str
    theorem_id: int
    name: str | None
    status: str
    remarks: str | None
    created_at: ApiDateTime
    updated_at: ApiDateTime

    model_config = {"from_attributes": True}


class LemmaDependencyOut(BaseModel):
    # The proof the step pinned (always verified), so a client can expand the
    # lemma's own dependencies from it without first listing the theorem's proofs.
    proof_id: int
    theorem: TheoremOut


class DirectDependenciesOut(BaseModel):
    axioms: list[AxiomOut]
    lemmas: list[LemmaDependencyOut]
    applied_proofs: dict[int, int] = Field(default_factory=dict)


class ProofCreate(BaseModel):
    theorem_id: int
    name: str | None = None
    remarks: str | None = None


class ProofStepCreate(BaseModel):
    kind: Literal[
        "premise",
        "assumption",
        "axiom",
        "theorem",
        "mp",
        "gen",
        "imp_intro",
    ]
    conclusion_formula_id: int | None = None

    # kind == "assumption": the assumed proposition is conclusion_formula_id.

    # kind == "premise"
    premise_ord: int | None = None

    # kind == "axiom"
    axiom_id: int | None = None

    # kind in ("axiom", "theorem")
    subst: SubstitutionIn = Field(default_factory=SubstitutionIn)

    # kind == "theorem"
    applied_proof_id: int | None = None
    arg_step_ords: list[int] = Field(default_factory=list)

    # kind == "mp"
    antecedent_step_ord: int | None = None
    implication_step_ord: int | None = None

    # kind in ("gen", "imp_intro")
    body_step_ord: int | None = None
    gen_variable_symbol_id: int | None = None

    # kind == "imp_intro"
    assumption_step_ord: int | None = None


class ProofStepOut(BaseModel):
    proof_id: int
    ord: int
    step_kind: str
    conclusion_formula: FormulaOut
    premise_ord: int | None
    axiom: AxiomOut | None
    applied_proof_id: int | None
    inference_rule: InferenceRuleOut | None
    gen_variable_symbol_id: int | None
    arg_step_ords: list[int]
    term_substs: list[TermSubstOut]
    prop_substs: list[PropSubstOut]
    remarks: str | None
    created_at: ApiDateTime


class ProofStatePremiseOut(BaseModel):
    ord: int
    tokens: list[TokenIn]
    used_by: list[int]


class ProofStateEstablishedOut(BaseModel):
    ord: int
    tokens: list[TokenIn]
    step_kind: str
    depends_on_premises: list[int]
    depends_on_assumptions: list[int]


class ProofStateOpenAssumptionOut(BaseModel):
    step_ord: int
    tokens: list[TokenIn]


class ProofStateOut(BaseModel):
    goal_tokens: list[TokenIn]
    premises: list[ProofStatePremiseOut]
    established: list[ProofStateEstablishedOut]
    open_assumptions: list[ProofStateOpenAssumptionOut]
    reached_goal: bool
    blocking: list[
        Literal["open_assumption", "goal_not_reached", "validation_failed"]
    ]


class ProofStepFollowupOut(BaseModel):
    kind: Literal["mp"]
    antecedent_step_ord: int
    implication_step_ord: int
    conclusion_tokens: list[TokenIn]
    reaches_goal: bool


class ValidateResultOut(BaseModel):
    status: str


class ComputeSubstitutedTokensRequest(BaseModel):
    formula_id: int
    subst: SubstitutionIn = Field(default_factory=SubstitutionIn)


class ComputeGenTokensRequest(BaseModel):
    body_formula_id: int
    gen_variable_symbol_id: int


class DefinitionOut(BaseModel):
    id: int
    public_id: str
    name: str
    kind: str
    new_symbol: SymbolOut
    display_formula: FormulaOut | None
    requires_existence_proof: bool
    requires_uniqueness_proof: bool
    description: str | None
    tags: list[TagOut] = Field(default_factory=list)
    remarks: str | None
    created_at: ApiDateTime

    model_config = {"from_attributes": True}


class DefinitionCreate(BaseModel):
    kind: Literal["predicate", "function", "logical", "quant_prop", "quant_term"]
    name: str
    param_symbol_ids: list[int] = Field(default_factory=list)
    body_formula_id: int
    requires_existence_proof: bool = False
    requires_uniqueness_proof: bool = False
    latex_template: str | None = Field(default=None, max_length=1000)
    remarks: str | None = None
