export interface Token {
  symbol_id?: number | null
  de_bruijn_index?: number | null
}

export interface FormulaType {
  id: number
  name: string
  code: 'term' | 'proposition'
  remarks: string | null
  created_at: string
}

export interface SymbolType {
  id: number
  name: string
  output_formula_type_id: number
  input_formula_type_id: number | null
  fixed_arity: number | null
  is_quantifier: boolean
  remarks: string | null
  created_at: string
}

export type NotationKind = 'prefix' | 'infix'

export interface Symbol {
  id: number
  public_id: string
  name: string
  symbol_type_id: number
  symbol_type: SymbolType
  arity: number
  is_primitive: boolean
  namespace_id: number
  namespace_name: string
  notation_kind: NotationKind
  precedence: number | null
  latex_template: string | null
  remarks: string | null
  created_at: string
  usage_count?: number
}

export interface SymbolAlias {
  id: number
  symbol_id: number
  alias: string
  source: 'builtin' | 'user'
}

export interface SymbolCreate {
  name: string
  symbol_type_id: number
  arity: number
  is_primitive?: boolean
  notation_kind?: NotationKind
  precedence?: number | null
  latex_template?: string | null
  remarks?: string | null
}

export interface FormulaToken extends Token {
  position: number
}

export interface Formula {
  id: number
  public_id: string
  formula_type_id: number
  formula_type: FormulaType
  hash: string
  token_count: number
  description: string | null
  remarks: string | null
  created_at: string
}

export interface FormulaDetail extends Formula {
    tokens: FormulaToken[]
  }

export interface NamedConclusions {
  axioms: { public_id: string; name: string; description: string | null }[]
  theorems: { public_id: string; name: string; description: string | null }[]
}

export interface FormulaParseResult {
  tokens: Token[]
  formula_id: number | null
}

export interface Tag {
  id: number
  name: string
  created_at: string
}

export interface Axiom {
  id: number
  public_id: string
  name: string
  namespace_name: string
  formula_id: number
  formula: Formula
  origin_kind: string
  definition_id: number | null
  description: string | null
  tags: Tag[]
  remarks: string | null
  created_at: string
}

export interface AxiomCreate {
  name: string
  formula_id: number
  description?: string | null
  remarks?: string | null
}

export interface AxiomSystem {
  id: number
  public_id: string
  namespace_id: number
  namespace_name: string
  name: string
  remarks: string | null
  comparison_rank: number | null
  created_at: string
}

export interface AxiomSystemCreate {
  name: string
  remarks?: string | null
}

export interface Theorem {
  id: number
  public_id: string
  namespace_id: number
  namespace_name: string
  name: string
  conclusion_formula_id: number
  conclusion_formula: Formula
  status: string
  description: string | null
  tags: Tag[]
  external_checks: ExternalCheck[]
  remarks: string | null
  created_at: string
  updated_at: string
}

export interface TheoremCreate {
  name: string
  conclusion_formula_id: number
  premise_formula_ids: number[]
  tag_ids?: number[]
  description?: string | null
  remarks?: string | null
}

export interface TheoremPremise {
  ord: number
  formula: Formula
}

export interface TermSubst {
  source_symbol_id: number
  target_formula_id: number
}

export interface PropSubst {
  source_symbol_id: number
  body_formula_id: number
  formal_param_symbol_ids: number[]
}

export interface Substitution {
  prop_substs: PropSubst[]
  term_substs: TermSubst[]
}

export const emptySubstitution: Substitution = { prop_substs: [], term_substs: [] }

export interface InferenceRule {
  id: number
  name: string
  kind: string
  tier: string
  elimination_procedure: string | null
  premise_count: number
  requires_variable_param: boolean
  remarks: string | null
  created_at: string
}

export interface Proof {
  id: number
  public_id: string
  theorem_id: number
  name: string | null
  status: string
  remarks: string | null
  created_at: string
  updated_at: string
}

export interface LemmaDependency {
  /** The verified proof the citing step pinned. */
  proof_id: number
  proof_public_id?: string
  theorem: Theorem
}

  export interface DirectDependencies {
    axioms: Axiom[]
    lemmas: LemmaDependency[]
    applied_proofs?: Record<string, number>
    applied_proof_public_ids?: Record<string, string>
  }

export interface ProofCreate {
  theorem_id: number
  name?: string | null
  remarks?: string | null
}

export type StepKind =
  | 'premise'
  | 'assumption'
  | 'axiom'
  | 'theorem'
  | 'mp'
  | 'gen'
  | 'imp_intro'

export interface ProofStepCreate {
  kind: StepKind
  conclusion_formula_id?: number | null
  premise_ord?: number | null
  axiom_id?: number | null
  subst?: Substitution
  applied_proof_id?: number | null
  arg_step_ords?: number[]
  antecedent_step_ord?: number | null
  implication_step_ord?: number | null
  body_step_ord?: number | null
  gen_variable_symbol_id?: number | null
  assumption_step_ord?: number | null
}

export interface StepSuggestion {
  applied_proof_id: number | null
  subst: Substitution
  undetermined: { symbol_id: number; name: string; reason: string }[]
  defaulted_to_identity: number[]
  conclusion_tokens: Token[] | null
  premise_count: number
  arg_candidates: number[][]
}

export interface BackwardStepSuggestion {
  match_depth: number
  applied_proof_id: number | null
  subst: Substitution
  undetermined: { symbol_id: number; name: string; reason: string }[]
  defaulted_to_identity: number[]
  application_conclusion_tokens: Token[]
  antecedent_goals: Token[][]
  intermediate_conclusions: Token[][]
  premise_count: number
  premise_goals: Token[][]
  arg_candidates: number[][]
}

export interface BackwardStepSuggestions {
  candidates: BackwardStepSuggestion[]
}

export interface ApplicableTheorem {
  theorem: Theorem
  is_schematic: boolean
  score: number
}

export interface ProofStep {
  proof_id: number
  ord: number
  step_kind: string
  conclusion_formula: Formula
  premise_ord: number | null
  axiom: Axiom | null
  applied_proof_id: number | null
  inference_rule: InferenceRule | null
  gen_variable_symbol_id: number | null
  arg_step_ords: number[]
  term_substs: TermSubst[]
  prop_substs: PropSubst[]
  remarks: string | null
  created_at: string
}

export interface ProofStatePremise {
  ord: number
  tokens: Token[]
  used_by: number[]
}

export interface ProofStateEstablished {
  ord: number
  tokens: Token[]
  step_kind: string
  depends_on_premises: number[]
  depends_on_assumptions: number[]
}

export interface ProofStateOpenAssumption {
  step_ord: number
  tokens: Token[]
}

export interface ProofState {
  goal_tokens: Token[]
  premises: ProofStatePremise[]
  established: ProofStateEstablished[]
  open_assumptions: ProofStateOpenAssumption[]
  reached_goal: boolean
  blocking: ('open_assumption' | 'goal_not_reached' | 'validation_failed')[]
}

export interface ProofStepFollowup {
  kind: 'mp'
  antecedent_step_ord: number
  implication_step_ord: number
  conclusion_tokens: Token[]
  reaches_goal: boolean
}

export interface ValidateResult {
  status: string
}

export type DefinitionKind =
  | 'predicate'
  | 'function'
  | 'function_desc'
  | 'logical'
  | 'quant_prop'
  | 'quant_term'
export type DefinitionCreateKind = 'predicate' | 'function' | 'logical' | 'quant_prop' | 'quant_term'

export interface Definition {
  id: number
  public_id: string
  namespace_id: number
  namespace_name: string
  name: string
  kind: DefinitionKind
  new_symbol: Symbol
  display_formula: Formula | null
  requires_existence_proof: boolean
  requires_uniqueness_proof: boolean
  description: string | null
  tags: Tag[]
  remarks: string | null
  created_at: string
}

export interface DefinitionCreate {
  kind: DefinitionCreateKind
  name: string
  param_symbol_ids: number[]
  body_formula_id: number
  requires_existence_proof?: boolean
  requires_uniqueness_proof?: boolean
  latex_template?: string | null
  remarks?: string | null
}

export interface ExplorationNote {
  theorem: Theorem
  proof: Proof
  premises: Formula[]
  step_count: number
  updated_at: string
}

export interface ExplorationDependencies {
  axioms: Axiom[]
  theorems: Theorem[]
}

export interface ExplorationPromotion {
  theorem: Theorem
  proof: Proof
}

export interface ExternalCheck {
  source_system: string
  library: string
  library_version: string
  library_commit: string
  declaration: string
  module: string
  file: string
  line: number
  check_model: string
  check_roundtrip: string
  check_toolchain: string | null
  checked_at: string | null
  license: string
  copyright: string | null
  authors: string | null
  upstream_origin: string
  source_axioms: string[]
  axiom_comparison: AxiomComparison | null
}

// The foundation's own Lean/DEM axiom-dependency comparison for one imported
// statement (import_record.axiom_comparison). The panel names no axiom itself.
export interface AxiomComparison {
  lean: string
  lean_axiom: string
  lean_axiom_note: string
  dem: string
  dem_unused_axiom: string
}

export interface ExternalSource {
  library: string
  library_version: string
  library_commit: string
  license: string
  imported_statements: number
  notice_status: 'absent' | 'present' | 'not_checked'
}
