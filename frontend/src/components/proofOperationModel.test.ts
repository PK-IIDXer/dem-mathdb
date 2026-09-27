import { describe, expect, it } from 'vitest'
import type { ProofOperationAction, ProofOperationState } from './proofOperationModel'
import { createProofOperationState, proofOperationReducer } from './proofOperationModel'
import { isProofPlanComplete } from './proofPlanModel'

const t = (symbolId: number) => [{ symbol_id: symbolId }]
const noSubst = { term_substs: [], prop_substs: [] }

function dispatch(state: ProofOperationState, action: ProofOperationAction): ProofOperationState {
  return proofOperationReducer(state, action)
}

function declaration(
  fields: Array<{ field: 'name' | 'premises' | 'premise' | 'conclusion'; label: string }>,
  proof: { mode: 'forward' } | { mode: 'plan'; goalSymbolId: number },
): ProofOperationState {
  let state = createProofOperationState()
  for (const field of fields) state = dispatch(state, { type: 'commit_declaration', ...field })
  return dispatch(state, proof.mode === 'plan'
    ? { type: 'start_proof', mode: 'plan', goalTokens: t(proof.goalSymbolId) }
    : { type: 'start_proof', mode: 'forward' })
}

function forward(state: ProofOperationState, label: string, verified = false): ProofOperationState {
  return dispatch(state, {
    type: 'commit_forward_step',
    label,
    resultStatus: verified ? 'verified' : 'draft',
  })
}

function plan(
  state: ProofOperationState,
  action: Extract<ProofOperationAction, { type: 'dispatch_plan' }>['action'],
  verified = false,
): ProofOperationState {
  return dispatch(state, {
    type: 'dispatch_plan',
    action,
    resultStatus: verified ? 'verified' : 'draft',
  })
}

function caseA(): ProofOperationState {
  let state = declaration([
    { field: 'name', label: '連言導入' },
    { field: 'premise', label: 'φ' },
    { field: 'premise', label: 'ψ' },
    { field: 'conclusion', label: 'φ ∧ ψ' },
  ], { mode: 'forward' })
  state = forward(state, '前提 1 をクリック')
  state = forward(state, '前提 2 をクリック')
  state = forward(state, '連言導入公理を選ぶ')
  state = forward(state, '最初の MP 提案を受ける')
  return forward(state, '次の MP 提案を受ける', true)
}

function caseB(): ProofOperationState {
  let state = declaration([
    { field: 'name', label: '全称除去' },
    { field: 'premise', label: '∀x.φ¹(x)' },
    { field: 'conclusion', label: 'φ¹(t)' },
  ], { mode: 'forward' })
  state = forward(state, '前提をクリック')
  state = forward(state, '全称除去公理を選ぶ')
  return forward(state, 'MP 提案を受ける', true)
}

function caseC(): ProofOperationState {
  let state = declaration([
    { field: 'conclusion', label: '(φ→ψ) → (¬ψ→¬φ)' },
  ], { mode: 'plan', goalSymbolId: 200 })
  for (const [holeId, formulaId, assumption, body, assumptionStepOrd] of [
    [0, 10, 201, 202, 0], [1, 11, 203, 204, 1],
  ] as const) {
    state = plan(state, { type: 'select_assumption', holeId, formulaId, tokens: t(assumption) })
    state = plan(state, { type: 'discharge', holeId, bodyGoalTokens: t(body), assumptionStepOrd })
  }
  state = plan(state, {
    type: 'apply', holeId: 2,
    application: { kind: 'mp', label: 'not-introduction MP', premiseCount: 2 },
    premiseGoals: [t(205), t(206)],
  })
  state = plan(state, { type: 'select_assumption', holeId: 3, formulaId: 12, tokens: t(207) })
  state = plan(state, { type: 'discharge', holeId: 3, bodyGoalTokens: t(208), assumptionStepOrd: 2 })
  state = plan(state, {
    type: 'apply', holeId: 5,
    application: { kind: 'mp', label: 'MP to bottom', premiseCount: 2 },
    premiseGoals: [t(209), t(210)],
  })
  state = plan(state, {
    type: 'apply', holeId: 6,
    application: { kind: 'mp', label: 'derive psi', premiseCount: 2 },
    premiseGoals: [t(207), t(201)],
  })
  state = plan(state, { type: 'fill', holeId: 8, label: 'assumed phi', stepOrd: 2 })
  state = plan(state, { type: 'fill', holeId: 9, label: 'assumed implication', stepOrd: 0, insertions: [
    { nodeId: 6, stepOrd: 3 },
  ] })
  state = plan(state, {
    type: 'apply', holeId: 7,
    application: { kind: 'mp', label: 'not-elim MP', premiseCount: 2 },
    premiseGoals: [t(203), t(211)],
  })
  state = plan(state, { type: 'fill', holeId: 10, label: 'assumed not-psi', stepOrd: 1 })
  state = plan(state, {
    type: 'apply', holeId: 11,
    application: { kind: 'axiom', label: 'not elimination', axiomId: 1, subst: noSubst, premiseCount: 0 },
    premiseGoals: [], insertions: [
      { nodeId: 11, stepOrd: 4 }, { nodeId: 7, stepOrd: 5 },
      { nodeId: 5, stepOrd: 6 }, { nodeId: 3, stepOrd: 7 },
    ],
  })
  return plan(state, {
    type: 'apply', holeId: 4,
    application: { kind: 'axiom', label: 'not introduction', axiomId: 2, subst: noSubst, premiseCount: 0 },
    premiseGoals: [], insertions: [
      { nodeId: 4, stepOrd: 8 }, { nodeId: 2, stepOrd: 9 },
      { nodeId: 1, stepOrd: 10 }, { nodeId: 0, stepOrd: 11 },
    ],
  }, true)
}

function caseD(): ProofOperationState {
  let state = declaration([
    { field: 'name', label: '二前提の定理適用' },
    { field: 'premises', label: '前提 2 本' },
    { field: 'conclusion', label: '二前提からの結論' },
  ], { mode: 'plan', goalSymbolId: 300 })
  state = plan(state, {
    type: 'apply', holeId: 0,
    application: { kind: 'theorem', label: '第一の二前提補題', appliedProofId: 30, subst: noSubst, premiseCount: 2 },
    premiseGoals: [t(301), t(302)],
    argumentCandidates: [[3, 30], [5, 50]],
  })
  state = plan(state, {
    type: 'apply', holeId: 1,
    application: { kind: 'theorem', label: 'right conjunction', appliedProofId: 31, subst: noSubst, premiseCount: 1 },
    premiseGoals: [t(303)], argumentCandidates: [[1]],
  })
  state = plan(state, {
    type: 'apply', holeId: 2,
    application: { kind: 'theorem', label: '第二の二前提補題', appliedProofId: 32, subst: noSubst, premiseCount: 2 },
    premiseGoals: [t(304), t(305)],
    argumentCandidates: [[2, 20], [4, 40]],
  })
  state = plan(state, {
    type: 'apply', holeId: 4,
    application: { kind: 'theorem', label: 'left conjunction', appliedProofId: 33, subst: noSubst, premiseCount: 1 },
    premiseGoals: [t(303)], argumentCandidates: [[1]],
  })
  state = plan(state, {
    type: 'apply', holeId: 6,
    application: { kind: 'theorem', label: '共有中間結果の導出', appliedProofId: 34, subst: noSubst, premiseCount: 1 },
    premiseGoals: [t(306)], argumentCandidates: [[0]],
  })
  state = plan(state, { type: 'fill', holeId: 7, label: 'premise 1', stepOrd: 0, insertions: [
    { nodeId: 6, stepOrd: 1 }, { nodeId: 4, stepOrd: 2 },
  ] })
  state = plan(state, { type: 'fill', holeId: 3, label: '共有中間結果の再利用', stepOrd: 1, insertions: [
    { nodeId: 1, stepOrd: 3 },
  ] })
  state = plan(state, { type: 'fill', holeId: 5, label: 'premise 2', stepOrd: 4 })
  state = plan(state, { type: 'select_argument', nodeId: 2, premiseIndex: 0, stepOrd: 2 })
  state = plan(state, { type: 'select_argument', nodeId: 2, premiseIndex: 1, stepOrd: 4, insertions: [
    { nodeId: 2, stepOrd: 5 },
  ] })
  state = plan(state, { type: 'select_argument', nodeId: 0, premiseIndex: 0, stepOrd: 3 })
  return plan(state, { type: 'select_argument', nodeId: 0, premiseIndex: 1, stepOrd: 5, insertions: [
    { nodeId: 0, stepOrd: 6 },
  ] }, true)
}

describe('Phase 2 proof operation budgets', () => {
  it('measures cases A, B, C, and D with one dispatch boundary through verified', () => {
    const cases = [
      { name: 'A', state: caseA(), expected: 10, limit: 10, planComplete: false },
      { name: 'B', state: caseB(), expected: 7, limit: 7, planComplete: false },
      { name: 'C', state: caseC(), expected: 17, limit: 20, planComplete: true },
      { name: 'D', state: caseD(), expected: 16, limit: 17, planComplete: true },
    ]

    for (const measured of cases) {
      expect(measured.state.operationCount, measured.name).toBe(measured.expected)
      expect(measured.state.operationCount, measured.name).toBeLessThanOrEqual(measured.limit)
      expect(measured.state.status, measured.name).toBe('verified')
      if (measured.planComplete) {
        expect(isProofPlanComplete(measured.state.proofPlan!), measured.name).toBe(true)
      }
    }
  })
})
