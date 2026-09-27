import type { BackwardStepSuggestion, ProofStepCreate, Substitution, Symbol, Token } from '../api/types'
import { serialize, tokensToTree } from './FormulaEditor/model'

/** Canonical token shape used inside a proof plan and in its API requests. */
export function normalizeTokens(tokens: Token[]): Token[] {
  return tokens.map((token) => ({
    symbol_id: token.symbol_id ?? null,
    de_bruijn_index: token.de_bruijn_index ?? null,
  }))
}

export function sameTokens(left: Token[], right: Token[]): boolean {
  const normalizedLeft = normalizeTokens(left)
  const normalizedRight = normalizeTokens(right)
  return normalizedLeft.length === normalizedRight.length
    && normalizedLeft.every((token, index) => (
      token.symbol_id === normalizedRight[index].symbol_id
        && token.de_bruijn_index === normalizedRight[index].de_bruijn_index
    ))
}

/** Returns the consequent when the selected formula matches an implication antecedent. */
export function implicationBodyForAssumption(
  goalTokens: Token[],
  assumptionTokens: Token[],
  implicationSymbolId: number,
  symbolsById: Map<number, Symbol>,
): Token[] | null {
  const root = tokensToTree(goalTokens, symbolsById).tree
  if (root?.kind !== 'symbol' || root.symbolId !== implicationSymbolId) return null
  const antecedent = serialize(root.children[0] ?? null)?.tokens
  const consequent = serialize(root.children[1] ?? null)?.tokens
  if (antecedent == null || consequent == null) return null
  return sameTokens(antecedent, assumptionTokens) ? normalizeTokens(consequent) : null
}

export interface PlanFailure {
  nodeId: number
  message: string
}

export interface PlanInsertion {
  nodeId: number
  stepOrd: number
}

interface PlanNodeBase {
  id: number
  goalTokens: Token[]
  error: string | null
}

export interface PlanHoleNode extends PlanNodeBase {
  kind: 'hole'
  assumptionSelection: {
    formulaId: number
    tokens: Token[]
  } | null
}

export interface PlanFilledNode extends PlanNodeBase {
  kind: 'filled'
  label: string
  stepOrd: number
}

export type PlanApplication =
  | {
      kind: 'theorem'
      label: string
      appliedProofId: number
      subst: Substitution
      premiseCount: number
    }
  | {
      kind: 'axiom'
      label: string
      axiomId: number
      subst: Substitution
      premiseCount: 0
    }
  | { kind: 'mp'; label: string; premiseCount: 2 }
  | { kind: 'gen'; label: string; variableSymbolId: number; premiseCount: 1 }

export interface PlanApplicationNode extends PlanNodeBase {
  kind: 'plan'
  application: PlanApplication
  premises: ProofPlanNode[]
  /** Server candidates in premise order. A singleton is selected for free. */
  argumentCandidates: number[][]
  argumentSelections: Array<number | null>
  stepOrd: number | null
}

/** A binder, not another premise-bearing application.
 *
 * The assumption is inserted when this node is created. The sole child is the
 * goal proved under that assumption; when it fills, =>I discharges the stored
 * assumption step.
 */
export interface PlanDischargeNode extends PlanNodeBase {
  kind: 'discharge'
  assumptionFormulaId: number
  assumptionTokens: Token[]
  assumptionStepOrd: number
  body: ProofPlanNode
  stepOrd: number | null
}

export type ProofPlanNode =
  | PlanHoleNode
  | PlanFilledNode
  | PlanApplicationNode
  | PlanDischargeNode

export interface ProofPlanState {
  root: ProofPlanNode
  nextNodeId: number
  /** Incremented only by reducer actions, each of which is one user commit. */
  operationCount: number
}

interface OperationOutcome {
  insertions?: PlanInsertion[]
  failure?: PlanFailure
}

export type ProofPlanAction =
  | ({
      type: 'select_assumption'
      holeId: number
      formulaId: number
      tokens: Token[]
    } & OperationOutcome)
  | ({
      type: 'apply'
      holeId: number
      application: PlanApplication
      /** Instantiated by the server-provided substitution, in premise order. */
      premiseGoals: Token[][]
      /** `suggest_step.arg_candidates`, in premise order. */
      argumentCandidates?: number[][]
    } & OperationOutcome)
  | ({
      type: 'apply_backward'
      holeId: number
      application: Extract<PlanApplication, { kind: 'axiom' | 'theorem' }>
      recipe: BackwardStepSuggestion
    } & OperationOutcome)
  | ({
      type: 'select_argument'
      nodeId: number
      premiseIndex: number
      stepOrd: number
    } & OperationOutcome)
  | ({
      type: 'fill'
      holeId: number
      label: string
      stepOrd: number
    } & OperationOutcome)
  | ({
      type: 'discharge'
      holeId: number
      bodyGoalTokens: Token[]
      assumptionStepOrd: number
    } & OperationOutcome)
  | ({ type: 'failed'; holeId: number; message: string } & OperationOutcome)

export interface ReadyPlanStep {
  nodeId: number
  input: ProofStepCreate
}

export function createProofPlan(goalTokens: Token[]): ProofPlanState {
  return {
    root: hole(0, goalTokens),
    nextNodeId: 1,
    operationCount: 0,
  }
}

function hole(id: number, goalTokens: Token[]): PlanHoleNode {
  return {
    id,
    kind: 'hole',
    goalTokens: normalizeTokens(goalTokens),
    assumptionSelection: null,
    error: null,
  }
}

function replaceNode(
  node: ProofPlanNode,
  id: number,
  replacement: (current: ProofPlanNode) => ProofPlanNode,
): ProofPlanNode {
  if (node.id === id) return replacement(node)
  if (node.kind === 'plan') {
    return { ...node, premises: node.premises.map((child) => replaceNode(child, id, replacement)) }
  }
  if (node.kind === 'discharge') {
    return { ...node, body: replaceNode(node.body, id, replacement) }
  }
  return node
}

export function applyInsertionRecords(
  node: ProofPlanNode,
  insertions: PlanInsertion[],
  failure?: PlanFailure,
): ProofPlanNode {
  const insertionById = new Map(insertions.map((item) => [item.nodeId, item.stepOrd]))

  function visit(current: ProofPlanNode): ProofPlanNode {
    const error = failure?.nodeId === current.id ? failure.message : current.error
    if (current.kind === 'plan') {
      return {
        ...current,
        error,
        stepOrd: insertionById.get(current.id) ?? current.stepOrd,
        premises: current.premises.map(visit),
      }
    }
    if (current.kind === 'discharge') {
      return {
        ...current,
        error,
        stepOrd: insertionById.get(current.id) ?? current.stepOrd,
        body: visit(current.body),
      }
    }
    return { ...current, error }
  }

  return visit(node)
}

export function proofPlanReducer(state: ProofPlanState, action: ProofPlanAction): ProofPlanState {
  let nextNodeId = state.nextNodeId
  let root = state.root

  if (action.type === 'select_assumption') {
    root = replaceNode(root, action.holeId, (node) => {
      if (node.kind !== 'hole') return node
      return {
        ...node,
        assumptionSelection: { formulaId: action.formulaId, tokens: normalizeTokens(action.tokens) },
        error: null,
      }
    })
  } else if (action.type === 'apply') {
    if (action.application.premiseCount !== action.premiseGoals.length) {
      throw new Error(
        `suggest_step returned ${action.application.premiseCount} premises, `
          + `but ${action.premiseGoals.length} instantiated goals were supplied`,
      )
    }
    root = replaceNode(root, action.holeId, (node) => {
      if (node.kind !== 'hole') return node
      const premises = action.premiseGoals.map((goalTokens) => hole(nextNodeId++, goalTokens))
      const argumentCandidates = action.premiseGoals.map(
        (_, index) => action.argumentCandidates?.[index] ?? [],
      )
      return {
        id: node.id,
        kind: 'plan',
        goalTokens: node.goalTokens,
        application: action.application,
        premises,
        argumentCandidates,
        argumentSelections: argumentCandidates.map((candidates) => (
          candidates.length === 1 ? candidates[0] : null
        )),
        stepOrd: null,
        error: null,
      }
    })
  } else if (action.type === 'apply_backward') {
    const recipe = action.recipe
    if (action.application.premiseCount !== recipe.premise_goals.length) {
      throw new Error(
        `backward suggestion returned ${action.application.premiseCount} premises, `
          + `but ${recipe.premise_goals.length} instantiated goals were supplied`,
      )
    }
    if (
      recipe.match_depth !== recipe.antecedent_goals.length
      || recipe.match_depth !== recipe.intermediate_conclusions.length
    ) {
      throw new Error('backward suggestion depth does not match its MP recipe')
    }
    root = replaceNode(root, action.holeId, (node) => {
      const sourceId = recipe.match_depth === 0 ? node.id : nextNodeId++
      const argumentCandidates = recipe.premise_goals.map(
        (_, index) => recipe.arg_candidates[index] ?? [],
      )
      let subtree: ProofPlanNode = {
        id: sourceId,
        kind: 'plan',
        goalTokens: normalizeTokens(recipe.application_conclusion_tokens),
        application: action.application,
        premises: recipe.premise_goals.map((tokens) => hole(nextNodeId++, tokens)),
        argumentCandidates,
        argumentSelections: argumentCandidates.map((candidates) => (
          candidates.length === 1 ? candidates[0] : null
        )),
        stepOrd: null,
        error: null,
      }
      for (let index = 0; index < recipe.match_depth; index += 1) {
        const isRoot = index === recipe.match_depth - 1
        subtree = {
          id: isRoot ? node.id : nextNodeId++,
          kind: 'plan',
          goalTokens: normalizeTokens(recipe.intermediate_conclusions[index]),
          application: { kind: 'mp', label: `MP ${index + 1}`, premiseCount: 2 },
          premises: [hole(nextNodeId++, recipe.antecedent_goals[index]), subtree],
          argumentCandidates: [[], []],
          argumentSelections: [null, null],
          stepOrd: null,
          error: null,
        }
      }
      return subtree
    })
  } else if (action.type === 'select_argument') {
    root = replaceNode(root, action.nodeId, (node) => {
      if (node.kind !== 'plan') return node
      const candidates = node.argumentCandidates[action.premiseIndex] ?? []
      if (candidates.length < 2 || !candidates.includes(action.stepOrd)) {
        throw new Error(
          `step ${action.stepOrd} is not an ambiguous candidate for premise ${action.premiseIndex}`,
        )
      }
      const argumentSelections = [...node.argumentSelections]
      argumentSelections[action.premiseIndex] = action.stepOrd
      return { ...node, argumentSelections, error: null }
    })
  } else if (action.type === 'fill') {
    root = replaceNode(root, action.holeId, (node) => {
      if (node.kind !== 'hole') return node
      return {
        id: node.id,
        kind: 'filled',
        goalTokens: node.goalTokens,
        label: action.label,
        stepOrd: action.stepOrd,
        error: null,
      }
    })
  } else if (action.type === 'discharge') {
    root = replaceNode(root, action.holeId, (node) => {
      if (node.kind !== 'hole' || node.assumptionSelection === null) return node
      return {
        id: node.id,
        kind: 'discharge',
        goalTokens: node.goalTokens,
        assumptionFormulaId: node.assumptionSelection.formulaId,
        assumptionTokens: node.assumptionSelection.tokens,
        assumptionStepOrd: action.assumptionStepOrd,
        body: hole(nextNodeId++, action.bodyGoalTokens),
        stepOrd: null,
        error: null,
      }
    })
  } else {
    root = replaceNode(root, action.holeId, (node) => ({ ...node, error: action.message }))
  }

  for (const insertion of action.insertions ?? []) {
    const ready = nextReadyPlanStep(root)
    if (ready?.nodeId !== insertion.nodeId) {
      throw new Error(`plan node ${insertion.nodeId} is not the next dependency-ready insertion`)
    }
    root = applyInsertionRecords(root, [insertion])
  }
  if (action.failure !== undefined) {
    const ready = nextReadyPlanStep(root)
    if (ready?.nodeId !== action.failure.nodeId) {
      throw new Error(`failed plan node ${action.failure.nodeId} is not dependency-ready`)
    }
    root = applyInsertionRecords(root, [], action.failure)
  }
  return { root, nextNodeId, operationCount: state.operationCount + 1 }
}

export function nodeStepOrd(node: ProofPlanNode): number | null {
  if (node.kind === 'filled') return node.stepOrd
  if (node.kind === 'plan' || node.kind === 'discharge') return node.stepOrd
  return null
}

/** Returns one dependency-ready step in leaf-to-root order. */
export function nextReadyPlanStep(root: ProofPlanNode): ReadyPlanStep | null {
  function visit(node: ProofPlanNode): ReadyPlanStep | null {
    if (node.kind === 'hole' || node.kind === 'filled') return null
    if (node.kind === 'discharge') {
      const child = visit(node.body)
      if (child !== null) return child
      const bodyOrd = nodeStepOrd(node.body)
      return node.stepOrd === null && bodyOrd !== null
        ? {
            nodeId: node.id,
            input: {
              kind: 'imp_intro',
              assumption_step_ord: node.assumptionStepOrd,
              body_step_ord: bodyOrd,
            },
          }
        : null
    }

    const dependencies = node.application.kind === 'mp'
      ? [node.premises[1], node.premises[0]]
      : node.premises
    for (const premise of dependencies) {
      const child = visit(premise)
      if (child !== null) return child
    }
    if (node.stepOrd !== null) return null
    const argumentOrds = node.premises.map(nodeStepOrd)
    if (argumentOrds.some((ord) => ord === null)) return null
    const unresolvedAmbiguity = node.argumentCandidates.some((candidates, index) => (
      candidates.length >= 2 && node.argumentSelections[index] === null
    ))
    if (unresolvedAmbiguity) return null
    const ords = (argumentOrds as number[]).map(
      (ord, index) => node.argumentSelections[index] ?? ord,
    )
    const application = node.application
    if (application.kind === 'theorem') {
      return {
        nodeId: node.id,
        input: {
          kind: 'theorem',
          applied_proof_id: application.appliedProofId,
          subst: application.subst,
          arg_step_ords: ords,
        },
      }
    }
    if (application.kind === 'axiom') {
      return {
        nodeId: node.id,
        input: { kind: 'axiom', axiom_id: application.axiomId, subst: application.subst },
      }
    }
    if (application.kind === 'mp') {
      return {
        nodeId: node.id,
        input: { kind: 'mp', antecedent_step_ord: ords[0], implication_step_ord: ords[1] },
      }
    }
    return {
      nodeId: node.id,
      input: { kind: 'gen', body_step_ord: ords[0], gen_variable_symbol_id: application.variableSymbolId },
    }
  }

  return visit(root)
}

export function isProofPlanComplete(state: ProofPlanState): boolean {
  return nodeStepOrd(state.root) !== null
}

export function listPlanHoles(root: ProofPlanNode): PlanHoleNode[] {
  if (root.kind === 'hole') return [root]
  if (root.kind === 'plan') {
    const dependencies = root.application.kind === 'mp'
      ? [root.premises[1], root.premises[0]]
      : root.premises
    return dependencies.flatMap(listPlanHoles)
  }
  if (root.kind === 'discharge') return listPlanHoles(root.body)
  return []
}

export function findPlanNode(root: ProofPlanNode, id: number): ProofPlanNode | null {
  if (root.id === id) return root
  if (root.kind === 'plan') {
    for (const premise of root.premises) {
      const found = findPlanNode(premise, id)
      if (found !== null) return found
    }
  }
  if (root.kind === 'discharge') return findPlanNode(root.body, id)
  return null
}
