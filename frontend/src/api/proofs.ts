import { api } from './client'
import type {
  Axiom,
  BackwardStepSuggestions,
  DirectDependencies,
  FormulaDetail,
  InferenceRule,
  Proof,
  ProofCreate,
  ProofStep,
  ProofStepCreate,
  ProofState,
  ProofStepFollowup,
  Substitution,
  StepSuggestion,
  Token,
  ValidateResult,
} from './types'

export const proofsApi = {
  listInferenceRules: () => api.get<InferenceRule[]>('/inference-rules'),
  create: (body: ProofCreate) => api.post<Proof>('/proofs', body),
  get: (ref: number | string, signal?: AbortSignal) => api.get<Proof>(`/proofs/${ref}`, { signal }),
  listForTheorem: (theoremId: number) => api.get<Proof[]>(`/theorems/${theoremId}/proofs`),
  addStep: (proofId: number, body: ProofStepCreate) =>
    api.post<ProofStep>(`/proofs/${proofId}/steps`, body),
  listSteps: (proofId: number) => api.get<ProofStep[]>(`/proofs/${proofId}/steps`),
  getState: (proofId: number) => api.get<ProofState>(`/proofs/${proofId}/state`),
  listStepFollowups: (proofId: number, stepOrd: number) =>
    api.get<ProofStepFollowup[]>(`/proofs/${proofId}/steps/${stepOrd}/followups`),
  // Every conclusion formula of the proof, with tokens, in one response. A step
  // carries only the lightweight Formula, so rendering them one id at a time
  // costs one request per distinct formula.
  listFormulas: (proofId: number) => api.get<FormulaDetail[]>(`/proofs/${proofId}/formulas`),
  validate: (proofId: number) => api.post<ValidateResult>(`/proofs/${proofId}/validate`, undefined),
  // Axioms and lemma theorems (with name/status) cited directly by the proof, in
  // one response instead of one request per applied proof and per lemma.
  listDirectDependencies: (proofId: number) =>
    api.get<DirectDependencies>(`/proofs/${proofId}/direct-dependencies`),
  listUsedAxioms: (proofId: number) => api.get<Axiom[]>(`/proofs/${proofId}/used-axioms`),
  isValidInSystem: (proofId: number, axiomSystemId: number) =>
    api.get<{ is_subset: boolean }>(`/proofs/${proofId}/is-valid-in-system/${axiomSystemId}`),
  computeSubstitutedTokens: (formulaId: number, subst: Substitution) =>
    api.post<Token[]>('/proofs/compute-substituted-tokens', { formula_id: formulaId, subst }),
  computeGenTokens: (bodyFormulaId: number, genVariableSymbolId: number) =>
    api.post<Token[]>('/proofs/compute-gen-tokens', {
      body_formula_id: bodyFormulaId,
      gen_variable_symbol_id: genVariableSymbolId,
    }),
  suggestStep: (
    proofId: number,
    body: {
      kind: 'axiom' | 'theorem'
      applied_theorem_id?: number
      axiom_id?: number
      arg_step_ords?: number[]
      goal_tokens?: Token[] | null
    },
  ) => api.post<StepSuggestion>(`/proofs/${proofId}/steps/suggest`, body),
  suggestBackward: (
    proofId: number,
    body: {
      kind: 'axiom' | 'theorem'
      applied_theorem_id?: number
      axiom_id?: number
      goal_tokens: Token[]
      subst?: Substitution
    },
  ) => api.post<BackwardStepSuggestions>(`/proofs/${proofId}/steps/suggest-backward`, body),
}
