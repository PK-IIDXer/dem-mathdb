import { describe, expect, it } from 'vitest'
import { createProofOperationState, proofOperationReducer } from './proofOperationModel'

function countSelectedStepApplication(manualSubstitutions: number, ambiguousArguments = 0): number {
  let state = proofOperationReducer(createProofOperationState(), { type: 'start_proof', mode: 'forward' })
  const start = state.operationCount
  for (const label of [
    'この step に推論定理を使う',
    '推論定理を選ぶ',
    ...Array.from({ length: ambiguousArguments }, (_, index) => `前提 ${index + 1} の候補を選ぶ`),
    ...Array.from({ length: manualSubstitutions }, (_, index) => `未決定代入 ${index + 1} を指定`),
    'theorem step を追加',
  ]) {
    state = proofOperationReducer(state, { type: 'commit_forward_step', label })
  }
  return state.operationCount - start
}

describe('inference rule selected-step operation mapping', () => {
  it('does not add a commit to the existing four representative flows', () => {
    // The selected-step action replaces the old switch-to-lemma action.
    expect(countSelectedStepApplication(1)).toBe(4) // universal elimination: t is not automatic
    expect(countSelectedStepApplication(0)).toBe(3) // conjunction elimination
    expect(countSelectedStepApplication(0)).toBe(3) // biconditional elimination
    expect(countSelectedStepApplication(0)).toBe(3) // relative universal elimination
    expect(countSelectedStepApplication(0, 1)).toBe(4) // explicit ambiguous argument
  })
})
