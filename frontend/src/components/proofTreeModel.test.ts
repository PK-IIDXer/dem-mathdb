import { describe, expect, it } from 'vitest'
import type { ProofStep } from '../api/types'
import { buildProofTree, proofTreeRuleLabel } from './proofTreeModel'

function step(ord: number, argStepOrds: number[] = [], ruleKind: string | null = null): ProofStep {
  return {
    proof_id: 1,
    ord,
    step_kind: ruleKind === null ? 'assumption' : 'rule',
    conclusion_formula: { id: ord + 1 } as ProofStep['conclusion_formula'],
    premise_ord: null,
    axiom: null,
    applied_proof_id: null,
    inference_rule:
      ruleKind === null
        ? null
        : ({ id: 1, name: ruleKind, kind: ruleKind } as ProofStep['inference_rule']),
    gen_variable_symbol_id: null,
    arg_step_ords: argStepOrds,
    term_substs: [],
    prop_substs: [],
    remarks: null,
    created_at: '',
  }
}

describe('buildProofTree', () => {
  it('builds the final MP step from both referenced derivations', () => {
    const tree = buildProofTree([step(0), step(1), step(2, [0, 1], 'modus_ponens')])
    expect(tree.root?.step.ord).toBe(2)
    expect(tree.root?.children.map((child) => child.step.ord)).toEqual([0, 1])
    expect(tree.omittedStepOrds).toEqual([])
    expect(proofTreeRuleLabel(tree.root!)).toBe('MP')
  })

  it('draws implication introduction above its body and labels the discharged assumption', () => {
    const tree = buildProofTree([step(0), step(1, [0], 'generalization'), step(2, [0, 1], 'implication_intro')])
    expect(tree.root?.children.map((child) => child.step.ord)).toEqual([1])
    expect(tree.root?.children[0].children[0].step.ord).toBe(0)
    expect(proofTreeRuleLabel(tree.root!)).toBe('⇒導入, 仮定 (0) 解消')
  })

  it('collapses a shared derivation after its first expansion', () => {
    const tree = buildProofTree([
      step(0),
      step(1, [0], 'generalization'),
      step(2, [0, 1], 'modus_ponens'),
    ])
    expect(tree.root?.children[0].isReference).toBe(false)
    expect(tree.root?.children[1].children[0].isReference).toBe(true)
  })

  it('reports steps that are not used by the final conclusion', () => {
    const tree = buildProofTree([step(0), step(1), step(2, [1], 'generalization')])
    expect(tree.omittedStepOrds).toEqual([0])
  })

  it('does not report a vacuously discharged assumption as unreferenced', () => {
    // =>I weakening: the body never used the assumption it discharges, so the
    // assumption is drawn nowhere -- but its own =>I still names it.
    const tree = buildProofTree([step(0), step(1), step(2, [0, 1], 'implication_intro')])
    expect(tree.root?.children.map((child) => child.step.ord)).toEqual([1])
    expect(tree.omittedStepOrds).toEqual([])
  })

  it('marks discharged assumptions and leaves open ones unmarked', () => {
    const tree = buildProofTree([step(0), step(1), step(2, [0, 1], 'implication_intro')])
    // ord 0 is discharged but not drawn; ord 1 is an assumption nothing discharges
    expect(tree.root?.isDischarged).toBe(false)
    expect(tree.root?.children[0].isDischarged).toBe(false)

    const used = buildProofTree([
      step(0),
      step(1, [0], 'generalization'),
      step(2, [0, 1], 'implication_intro'),
    ])
    expect(used.root?.children[0].children[0].step.ord).toBe(0)
    expect(used.root?.children[0].children[0].isDischarged).toBe(true)
  })
})
