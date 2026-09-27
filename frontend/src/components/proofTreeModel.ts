import type { ProofStep } from '../api/types'

export interface ProofTreeNode {
  step: ProofStep
  children: ProofTreeNode[]
  isReference: boolean
  /** An assumption that some =>I in this proof discharges: drawn as `[φ]`. */
  isDischarged: boolean
}

export interface ProofTree {
  root: ProofTreeNode | null
  omittedStepOrds: number[]
}

function isImplicationIntro(step: ProofStep): boolean {
  return step.step_kind === 'rule' && step.inference_rule?.kind === 'implication_intro'
}

function premiseOrds(step: ProofStep): number[] {
  if (isImplicationIntro(step)) {
    // The assumption is already part of the body derivation.  Drawing it as a
    // second direct premise of =>I would duplicate it beside that derivation.
    return step.arg_step_ords.length >= 2 ? [step.arg_step_ords[1]] : []
  }
  return step.arg_step_ords
}

/** The assumption ord a step discharges, if it is an =>I.
 *
 * `premiseOrds` drops it, so it is not drawn as a premise. It is still spoken
 * for: a discharge that the body never used would otherwise be reported as an
 * unreferenced step while its own =>I labels it as discharged.
 */
function dischargedOrds(step: ProofStep): number[] {
  return isImplicationIntro(step) && step.arg_step_ords.length >= 1
    ? [step.arg_step_ords[0]]
    : []
}

/** Reconstruct the derivation rooted at the final proof step.
 *
 * Proof steps form a DAG. A mathematical proof tree normally copies a shared
 * derivation each time it is used, but doing so can make a generated diagram
 * exponentially large. The first occurrence is expanded and later occurrences
 * become explicit reference leaves.
 */
export function buildProofTree(steps: ProofStep[]): ProofTree {
  if (steps.length === 0) return { root: null, omittedStepOrds: [] }

  const byOrd = new Map(steps.map((step) => [step.ord, step]))
  const expanded = new Set<number>()
  const used = new Set<number>()
  const discharged = new Set<number>()
  for (const step of steps) {
    for (const ord of dischargedOrds(step)) discharged.add(ord)
  }

  function visit(ord: number, ancestors: Set<number>): ProofTreeNode | null {
    const step = byOrd.get(ord)
    if (!step) return null
    used.add(ord)
    for (const dischargedOrd of dischargedOrds(step)) used.add(dischargedOrd)
    const isDischarged = step.step_kind === 'assumption' && discharged.has(step.ord)

    if (ancestors.has(ord) || expanded.has(ord)) {
      return { step, children: [], isReference: true, isDischarged }
    }

    expanded.add(ord)
    const nextAncestors = new Set(ancestors)
    nextAncestors.add(ord)
    const children = premiseOrds(step)
      .map((premiseOrd) => visit(premiseOrd, nextAncestors))
      .filter((node): node is ProofTreeNode => node !== null)
    return { step, children, isReference: false, isDischarged }
  }

  const root = visit(steps[steps.length - 1].ord, new Set())
  const omittedStepOrds = steps.map((step) => step.ord).filter((ord) => !used.has(ord))
  return { root, omittedStepOrds }
}

export function proofTreeRuleLabel(node: ProofTreeNode): string {
  const { step } = node
  if (node.isReference) return `ステップ (${step.ord}) を再参照`

  switch (step.step_kind) {
    case 'premise':
      return `前提 ${step.premise_ord ?? '?'}`
    case 'assumption':
      return `仮定 (${step.ord})`
    case 'axiom':
      return `公理 ${step.axiom?.name ?? '?'}`
    case 'theorem':
      return `既証明 Proof #${step.applied_proof_id ?? '?'}`
    case 'rule':
      if (step.inference_rule?.kind === 'modus_ponens') return 'MP'
      if (step.inference_rule?.kind === 'generalization') return 'Gen'
      if (step.inference_rule?.kind === 'implication_intro') {
        return `⇒導入, 仮定 (${step.arg_step_ords[0] ?? '?'}) 解消`
      }
      return step.inference_rule?.name ?? step.inference_rule?.kind ?? '推論'
    default:
      return '推論'
  }
}
