import type { Token } from '../api/types'
import {
  createProofPlan,
  isProofPlanComplete,
  proofPlanReducer,
  type ProofPlanAction,
  type ProofPlanState,
} from './proofPlanModel'

export type DeclarationField = 'name' | 'premises' | 'premise' | 'conclusion'

export interface ProofOperationState {
  operationCount: number
  declarationCommits: Array<{ field: DeclarationField; label: string }>
  mode: 'forward' | 'plan' | null
  proofPlan: ProofPlanState | null
  status: 'declaring' | 'proving' | 'verified'
}

type ProofOperationResult = { resultStatus?: 'draft' | 'verified' }

export type ProofOperationAction =
  | { type: 'commit_declaration'; field: DeclarationField; label: string }
  | { type: 'start_proof'; mode: 'forward' }
  | { type: 'start_proof'; mode: 'plan'; goalTokens: Token[] }
  | ({ type: 'commit_forward_step'; label: string } & ProofOperationResult)
  | ({ type: 'dispatch_plan'; action: ProofPlanAction } & ProofOperationResult)

export function createProofOperationState(): ProofOperationState {
  return {
    operationCount: 0,
    declarationCommits: [],
    mode: null,
    proofPlan: null,
    status: 'declaring',
  }
}

/**
 * Counts one reducer dispatch as one discrete user commit from the first
 * declaration field through the response that reports the proof verified.
 */
export function proofOperationReducer(
  state: ProofOperationState,
  action: ProofOperationAction,
): ProofOperationState {
  if (state.status === 'verified') {
    throw new Error('cannot count another operation after verification')
  }

  if (action.type === 'commit_declaration') {
    if (state.status !== 'declaring') throw new Error('declaration is already complete')
    return {
      ...state,
      operationCount: state.operationCount + 1,
      declarationCommits: [
        ...state.declarationCommits,
        { field: action.field, label: action.label },
      ],
    }
  }

  if (action.type === 'start_proof') {
    if (state.status !== 'declaring') throw new Error('proof has already started')
    return {
      ...state,
      operationCount: state.operationCount + 1,
      mode: action.mode,
      proofPlan: action.mode === 'plan' ? createProofPlan(action.goalTokens) : null,
      status: 'proving',
    }
  }

  if (state.status !== 'proving') {
    throw new Error('proof operation dispatched before starting the proof')
  }

  if (action.type === 'commit_forward_step') {
    if (state.mode !== 'forward') throw new Error('forward step dispatched for a proof plan')
    return {
      ...state,
      operationCount: state.operationCount + 1,
      status: action.resultStatus === 'verified' ? 'verified' : 'proving',
    }
  }

  if (state.mode !== 'plan' || state.proofPlan === null) {
    throw new Error('plan action dispatched for a forward proof')
  }
  const proofPlan = proofPlanReducer(state.proofPlan, action.action)
  if (action.resultStatus === 'verified' && !isProofPlanComplete(proofPlan)) {
    throw new Error('proof cannot be verified while its plan is incomplete')
  }
  return {
    ...state,
    operationCount: state.operationCount + 1,
    proofPlan,
    status: action.resultStatus === 'verified' ? 'verified' : 'proving',
  }
}
