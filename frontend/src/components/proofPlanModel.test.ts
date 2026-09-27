import { describe, expect, it } from 'vitest'
import type { FormulaToken, Symbol, SymbolType } from '../api/types'
import type { EditorNode, SymbolNode } from './FormulaEditor/model'
import { serialize } from './FormulaEditor/model'
import type { ProofPlanAction, ProofPlanState } from './proofPlanModel'
import {
  createProofPlan,
  implicationBodyForAssumption,
  nextReadyPlanStep,
  proofPlanReducer,
} from './proofPlanModel'

const t = (symbolId: number) => [{ symbol_id: symbolId }]
const noSubst = { term_substs: [], prop_substs: [] }

const formulaType: SymbolType = {
  id: 1,
  name: 'proposition',
  output_formula_type_id: 1,
  input_formula_type_id: 1,
  fixed_arity: null,
  is_quantifier: false,
  remarks: null,
  created_at: '',
}

function symbol(id: number, name: string, arity: number, isQuantifier = false): Symbol {
  return {
    id,
    public_id: `00000000-0000-0000-0000-${String(id).padStart(12, '0')}`,
    name,
    symbol_type_id: 1,
    symbol_type: { ...formulaType, is_quantifier: isQuantifier },
    arity,
    is_primitive: false,
    namespace_id: 1,
    namespace_name: 'dem.test',
    notation_kind: 'prefix',
    precedence: null,
    latex_template: null,
    remarks: null,
    created_at: '',
  }
}

const atom = (symbolId: number): SymbolNode => ({ id: symbolId, kind: 'symbol', symbolId, children: [] })
const app = (id: number, symbolId: number, ...children: EditorNode[]): SymbolNode => ({
  id,
  kind: 'symbol',
  symbolId,
  children,
})

function dispatch(state: ProofPlanState, action: ProofPlanAction): ProofPlanState {
  return proofPlanReducer(state, action)
}

describe('proofPlanReducer', () => {
  it('normalizes serialized and API tokens when they enter the plan', () => {
    let state = createProofPlan(t(1))
    expect(state.root.goalTokens).toEqual([
      { symbol_id: 1, de_bruijn_index: null },
    ])

    state = dispatch(state, {
      type: 'select_assumption',
      holeId: 0,
      formulaId: 10,
      tokens: [{ position: 0, symbol_id: 1, de_bruijn_index: null } as FormulaToken],
    })
    expect(state.root).toMatchObject({
      kind: 'hole',
      assumptionSelection: {
        tokens: [{ symbol_id: 1, de_bruijn_index: null }],
      },
    })
  })

  it('uses suggest_step premise_count as the plan arity', () => {
    const state = createProofPlan(t(1))
    expect(() => dispatch(state, {
      type: 'apply',
      holeId: 0,
      application: {
        kind: 'theorem', label: 'three premises', appliedProofId: 4, subst: noSubst, premiseCount: 3,
      },
      premiseGoals: [t(2), t(3)],
    })).toThrow(/returned 3 premises/)
  })

  it('defaults a unique argument for free and waits for every ambiguous selection', () => {
    let state = createProofPlan(t(1))
    state = dispatch(state, {
      type: 'apply', holeId: 0,
      application: { kind: 'theorem', label: 'arguments', appliedProofId: 4, subst: noSubst, premiseCount: 2 },
      premiseGoals: [t(2), t(3)],
      argumentCandidates: [[4], [5, 6]],
    })
    state = dispatch(state, { type: 'fill', holeId: 1, label: 'unique', stepOrd: 4 })
    state = dispatch(state, { type: 'fill', holeId: 2, label: 'ambiguous', stepOrd: 5 })
    expect(nextReadyPlanStep(state.root)).toBeNull()

    state = dispatch(state, { type: 'select_argument', nodeId: 0, premiseIndex: 1, stepOrd: 5 })
    expect(nextReadyPlanStep(state.root)).toEqual({
      nodeId: 0,
      input: {
        kind: 'theorem', applied_proof_id: 4, subst: noSubst, arg_step_ords: [4, 5],
      },
    })
    expect(state.operationCount).toBe(4)
  })

  it('returns dependency-ready applications from leaves toward the root', () => {
    let state = createProofPlan(t(1))
    state = dispatch(state, {
      type: 'apply', holeId: 0,
      application: { kind: 'mp', label: 'MP', premiseCount: 2 },
      premiseGoals: [t(2), t(3)],
    })
    state = dispatch(state, { type: 'fill', holeId: 1, label: 'left', stepOrd: 4 })
    expect(nextReadyPlanStep(state.root)).toBeNull()
    state = dispatch(state, { type: 'fill', holeId: 2, label: 'right', stepOrd: 5 })
    expect(nextReadyPlanStep(state.root)).toEqual({
      nodeId: 0,
      input: { kind: 'mp', antecedent_step_ord: 4, implication_step_ord: 5 },
    })
  })

  it('maps a theorem backward recipe to theorem premises followed by inner-to-outer MP holes', () => {
    const subst = {
      term_substs: [],
      prop_substs: [{ source_symbol_id: 90, body_formula_id: 91, formal_param_symbol_ids: [] }],
    }
    let state = createProofPlan(t(1))
    state = dispatch(state, {
      type: 'apply_backward',
      holeId: 0,
      application: {
        kind: 'theorem', label: 'implicational lemma', appliedProofId: 7, subst, premiseCount: 1,
      },
      recipe: {
        match_depth: 2,
        applied_proof_id: 7,
        subst,
        undetermined: [],
        defaulted_to_identity: [],
        application_conclusion_tokens: t(10),
        antecedent_goals: [t(11), t(12)],
        intermediate_conclusions: [t(13), t(1)],
        premise_count: 1,
        premise_goals: [t(14)],
        arg_candidates: [[]],
      },
    })

    expect(state.root).toMatchObject({
      id: 0,
      kind: 'plan',
      application: { kind: 'mp' },
      premises: [
        { kind: 'hole', goalTokens: [{ symbol_id: 12, de_bruijn_index: null }] },
        {
          kind: 'plan',
          application: { kind: 'mp' },
          premises: [
            { kind: 'hole', goalTokens: [{ symbol_id: 11, de_bruijn_index: null }] },
            {
              kind: 'plan',
              application: { kind: 'theorem' },
              premises: [
                { kind: 'hole', goalTokens: [{ symbol_id: 14, de_bruijn_index: null }] },
              ],
            },
          ],
        },
      ],
    })
    expect(state.operationCount).toBe(1)
    expect(nextReadyPlanStep(state.root)).toBeNull()
  })

  it('keeps a failed backward MP on that node and does not insert its parent discharge', () => {
    let state = createProofPlan(t(1))
    state = dispatch(state, {
      type: 'select_assumption', holeId: 0, formulaId: 20, tokens: t(2),
    })
    state = dispatch(state, {
      type: 'discharge', holeId: 0, bodyGoalTokens: t(3), assumptionStepOrd: 0,
    })
    state = dispatch(state, {
      type: 'apply_backward', holeId: 1,
      application: {
        kind: 'axiom', label: 'backward axiom', axiomId: 8, subst: noSubst, premiseCount: 0,
      },
      recipe: {
        match_depth: 1,
        applied_proof_id: null,
        subst: noSubst,
        undetermined: [],
        defaulted_to_identity: [],
        application_conclusion_tokens: t(4),
        antecedent_goals: [t(5)],
        intermediate_conclusions: [t(3)],
        premise_count: 0,
        premise_goals: [],
        arg_candidates: [],
      },
      insertions: [{ nodeId: 2, stepOrd: 1 }],
    })
    state = dispatch(state, {
      type: 'fill', holeId: 3, label: 'wrong antecedent', stepOrd: 2,
      failure: { nodeId: 1, message: 'selected arguments do not match' },
    })

    expect(state.root).toMatchObject({
      kind: 'discharge',
      stepOrd: null,
      body: { kind: 'plan', stepOrd: null, error: 'selected arguments do not match' },
    })
    expect(nextReadyPlanStep(state.root)).toMatchObject({ nodeId: 1 })
  })

  it('inserts the outer discharge immediately after a backward MP completes its body', () => {
    let state = createProofPlan(t(1))
    state = dispatch(state, {
      type: 'select_assumption', holeId: 0, formulaId: 20, tokens: t(2),
    })
    state = dispatch(state, {
      type: 'discharge', holeId: 0, bodyGoalTokens: t(3), assumptionStepOrd: 0,
    })
    state = dispatch(state, {
      type: 'apply_backward', holeId: 1,
      application: {
        kind: 'axiom', label: 'backward axiom', axiomId: 8, subst: noSubst, premiseCount: 0,
      },
      recipe: {
        match_depth: 1,
        applied_proof_id: null,
        subst: noSubst,
        undetermined: [],
        defaulted_to_identity: [],
        application_conclusion_tokens: t(4),
        antecedent_goals: [t(5)],
        intermediate_conclusions: [t(3)],
        premise_count: 0,
        premise_goals: [],
        arg_candidates: [],
      },
      insertions: [{ nodeId: 2, stepOrd: 1 }],
    })
    state = dispatch(state, {
      type: 'fill', holeId: 3, label: 'antecedent', stepOrd: 2,
      insertions: [{ nodeId: 1, stepOrd: 3 }, { nodeId: 0, stepOrd: 4 }],
    })

    expect(state.root).toMatchObject({ kind: 'discharge', stepOrd: 4 })
    expect(nextReadyPlanStep(state.root)).toBeNull()
  })
})

describe('implicationBodyForAssumption', () => {
  it('matches serialize tokens with an API formula whose empty fields are null', () => {
    const implication = symbol(10, '→', 2)
    const phi = symbol(11, 'φ', 0)
    const body = symbol(12, 'ψ', 0)
    const symbols = new Map([implication, phi, body].map((item) => [item.id, item]))
    const serializedGoal = serialize(app(20, implication.id, atom(phi.id), atom(body.id)))!.tokens
    const apiAssumption: FormulaToken[] = [
      { position: 0, symbol_id: phi.id, de_bruijn_index: null },
    ]

    expect(serializedGoal[1]).toEqual({ symbol_id: phi.id })
    expect(implicationBodyForAssumption(
      serializedGoal,
      apiAssumption,
      implication.id,
      symbols,
    )).toEqual([{ symbol_id: body.id, de_bruijn_index: null }])
  })

  it('matches API tokens when the antecedent contains a bound variable', () => {
    const implication = symbol(10, '→', 2)
    const forall = symbol(20, '∀', 1, true)
    const predicate = symbol(21, 'P', 1)
    const body = symbol(12, 'ψ', 0)
    const symbols = new Map([implication, forall, predicate, body].map((item) => [item.id, item]))
    const antecedent = app(
      30,
      forall.id,
      app(31, predicate.id, { id: 32, kind: 'bound', index: 0 }),
    )
    const serializedGoal = serialize(app(33, implication.id, antecedent, atom(body.id)))!.tokens
    const apiAssumption: FormulaToken[] = [
      { position: 0, symbol_id: forall.id, de_bruijn_index: null },
      { position: 1, symbol_id: predicate.id, de_bruijn_index: null },
      { position: 2, symbol_id: null, de_bruijn_index: 0 },
    ]

    expect(serializedGoal[3]).toEqual({ de_bruijn_index: 0 })
    expect(implicationBodyForAssumption(
      serializedGoal,
      apiAssumption,
      implication.id,
      symbols,
    )).toEqual([{ symbol_id: body.id, de_bruijn_index: null }])
  })
})
