import { useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'
import { formulasApi } from '../api/formulas'
import { proofsApi } from '../api/proofs'
import { theoremsApi } from '../api/theorems'
import type {
  Axiom,
  BackwardStepSuggestion,
  ProofState,
  Substitution,
  Symbol,
  Theorem,
  Token,
} from '../api/types'
import { ApiError } from '../api/client'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import { FormulaPicker } from './FormulaPicker'
import { Latex } from './Latex'
import { SubstitutionEditor } from './StepForm/SubstitutionEditor'
import { renderLatex, tokensToTree } from './FormulaEditor/model'
import { useCommand } from '../commands/CommandProvider'
import { InferenceRulePicker } from './InferenceRulePicker'
import {
  applyInsertionRecords,
  createProofPlan,
  findPlanNode,
  implicationBodyForAssumption,
  isProofPlanComplete,
  listPlanHoles,
  nextReadyPlanStep,
  proofPlanReducer,
  sameTokens,
  type PlanFailure,
  type PlanHoleNode,
  type PlanInsertion,
  type ProofPlanAction,
  type ProofPlanNode,
} from './proofPlanModel'

interface TopDownProofEditorProps {
  proofId: number
  proofState: ProofState
  symbols: Symbol[]
  context: Record<string, number>
  onAdded: () => void
  onOperationDispatch?: (action: ProofPlanAction) => void
  showRules?: boolean
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error
    ? error.message
    : 'plan を更新できませんでした'
}

export function TopDownProofEditor({
  proofId,
  proofState,
  symbols,
  context,
  onAdded,
  onOperationDispatch,
  showRules = true,
}: TopDownProofEditorProps) {
  const [state, reduce] = useReducer(proofPlanReducer, proofState.goal_tokens, createProofPlan)
  const editorRef = useRef<HTMLDivElement>(null)
  const [selectedHoleId, setSelectedHoleId] = useState(0)
  const [pending, setPending] = useState(false)
  const [focusRequest, setFocusRequest] = useState<{ holeId: number | null; sequence: number } | null>(null)
  const actionPanelRef = useRef<HTMLDivElement>(null)
  const planStatusRef = useRef<HTMLSpanElement>(null)
  const [backwardChoice, setBackwardChoice] = useState<{
    holeId: number
    kind: 'axiom' | 'theorem'
    label: string
    sourceId: number
    candidates: BackwardStepSuggestion[]
  } | null>(null)
  const [backwardEdit, setBackwardEdit] = useState<{
    holeId: number
    kind: 'axiom' | 'theorem'
    label: string
    sourceId: number
    candidate: BackwardStepSuggestion
    value: Substitution
  } | null>(null)
  const { data: theorems = [] } = useQuery({
    queryKey: ['theorems', 'top-down-picker'],
    queryFn: () => theoremsApi.listVisible({ status: 'proven' }),
  })
  const { data: axioms = [] } = useQuery({ queryKey: ['axioms'], queryFn: () => axiomsApi.list() })
  const symbolsById = useMemo(() => new Map(symbols.map((symbol) => [symbol.id, symbol])), [symbols])
  const holes = listPlanHoles(state.root)
  const selectedNode = findPlanNode(state.root, selectedHoleId)
  const selectedHole = selectedNode?.kind === 'hole' ? selectedNode : holes[0] ?? null
  const backwardRequiredIncomplete = backwardEdit?.candidate.undetermined.some((item) => {
    const term = backwardEdit.value.term_substs.find((subst) => subst.source_symbol_id === item.symbol_id)
    const prop = backwardEdit.value.prop_substs.find((subst) => subst.source_symbol_id === item.symbol_id)
    return (term?.target_formula_id ?? prop?.body_formula_id ?? 0) <= 0
  }) ?? false

  useLayoutEffect(() => {
    if (pending || focusRequest === null) return
    if (focusRequest.holeId === null) {
      planStatusRef.current?.focus()
    } else if (selectedHole?.id === focusRequest.holeId) {
      const control = actionPanelRef.current?.querySelector<HTMLElement>(
        'button:not(:disabled), select:not(:disabled), summary, input:not(:disabled), textarea:not(:disabled)',
      )
      control?.focus()
    } else {
      return
    }
    setFocusRequest(null)
  }, [focusRequest, pending, selectedHole?.id])

  function dispatch(action: ProofPlanAction): void {
    reduce(action)
    onOperationDispatch?.(action)
  }

  async function finishOperation(baseAction: ProofPlanAction): Promise<void> {
    if (baseAction.type !== 'apply_backward') setBackwardEdit(null)
    const preview = proofPlanReducer(state, baseAction)
    let workingRoot = preview.root
    const insertions: PlanInsertion[] = []
    let failure: PlanFailure | undefined

    while (true) {
      const ready = nextReadyPlanStep(workingRoot)
      if (ready === null) break
      try {
        const step = await proofsApi.addStep(proofId, ready.input)
        const insertion = { nodeId: ready.nodeId, stepOrd: step.ord }
        insertions.push(insertion)
        workingRoot = applyInsertionRecords(workingRoot, [insertion])
      } catch (error) {
        failure = { nodeId: ready.nodeId, message: errorMessage(error) }
        break
      }
    }

    dispatch({ ...baseAction, insertions, failure } as ProofPlanAction)
    if (insertions.length > 0) onAdded()
    const nextHoles = listPlanHoles(workingRoot)
    const nextHoleId = nextHoles[0]?.id ?? null
    if (nextHoleId !== null) setSelectedHoleId(nextHoleId)
    setFocusRequest((current) => ({ holeId: nextHoleId, sequence: (current?.sequence ?? 0) + 1 }))
  }

  function editableSubstitution(candidate: BackwardStepSuggestion): Substitution {
    const editableIds = new Set([
      ...candidate.defaulted_to_identity,
      ...candidate.undetermined.map((item) => item.symbol_id),
    ])
    const value: Substitution = {
      term_substs: candidate.subst.term_substs.filter((item) => editableIds.has(item.source_symbol_id)),
      prop_substs: candidate.subst.prop_substs.filter((item) => editableIds.has(item.source_symbol_id)),
    }
    const termVariables = symbols.filter(
      (symbol) => symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable,
    )
    for (const symbolId of editableIds) {
      const symbol = symbolsById.get(symbolId)
      if (symbol?.symbol_type.name === SYMBOL_TYPE.freeTermVariable) {
        if (!value.term_substs.some((item) => item.source_symbol_id === symbolId)) {
          value.term_substs.push({ source_symbol_id: symbolId, target_formula_id: 0 })
        }
      } else if (!value.prop_substs.some((item) => item.source_symbol_id === symbolId)) {
        value.prop_substs.push({
          source_symbol_id: symbolId,
          body_formula_id: 0,
          formal_param_symbol_ids: Array.from(
            { length: symbol?.arity ?? 0 },
            (_, index) => termVariables[index]?.id ?? termVariables[0]?.id ?? 0,
          ),
        })
      }
    }
    return value
  }

  function backwardAction(
    choice: { holeId: number; kind: 'axiom' | 'theorem'; label: string; sourceId: number },
    candidate: BackwardStepSuggestion,
  ): ProofPlanAction {
    if (choice.kind === 'theorem') {
      if (candidate.applied_proof_id == null) throw new Error('補題に verified proof がありません')
      return {
        type: 'apply_backward', holeId: choice.holeId,
        application: {
          kind: 'theorem', label: choice.label, appliedProofId: candidate.applied_proof_id,
          subst: candidate.subst, premiseCount: candidate.premise_count,
        },
        recipe: candidate,
      }
    }
    return {
      type: 'apply_backward', holeId: choice.holeId,
      application: {
        kind: 'axiom', label: choice.label, axiomId: choice.sourceId,
        subst: candidate.subst, premiseCount: 0,
      },
      recipe: candidate,
    }
  }

  async function acceptBackwardCandidate(
    choice: { holeId: number; kind: 'axiom' | 'theorem'; label: string; sourceId: number },
    candidate: BackwardStepSuggestion,
  ): Promise<void> {
    setBackwardChoice(null)
    const editable = candidate.defaulted_to_identity.length > 0 || candidate.undetermined.length > 0
    if (editable) {
      setBackwardEdit({ ...choice, candidate, value: editableSubstitution(candidate) })
      dispatch(backwardAction(choice, candidate))
    } else {
      setBackwardEdit(null)
      await finishOperation(backwardAction(choice, candidate))
    }
  }

  async function suggestBackward(
    hole: PlanHoleNode,
    kind: 'axiom' | 'theorem',
    source: Axiom | Theorem,
  ): Promise<void> {
    setPending(true)
    const choice = { holeId: hole.id, kind, label: source.name, sourceId: source.id }
    try {
      const result = await proofsApi.suggestBackward(proofId, {
        kind,
        ...(kind === 'axiom' ? { axiom_id: source.id } : { applied_theorem_id: source.id }),
        goal_tokens: hole.goalTokens,
      })
      if (result.candidates.length === 0) {
        dispatch({ type: 'failed', holeId: hole.id, message: 'この goal に一致する backward recipe がありません' })
      } else if (result.candidates.length === 1) {
        await acceptBackwardCandidate(choice, result.candidates[0])
      } else {
        setBackwardChoice({ ...choice, candidates: result.candidates })
      }
    } catch (error) {
      dispatch({ type: 'failed', holeId: hole.id, message: errorMessage(error) })
    } finally {
      setPending(false)
    }
  }

  async function updateBackwardSubstitution(value: Substitution): Promise<void> {
    if (backwardEdit == null) return
    setBackwardEdit({ ...backwardEdit, value })
    const required = new Set(backwardEdit.candidate.undetermined.map((item) => item.symbol_id))
    const completeIds = new Set([
      ...value.term_substs.filter((item) => item.target_formula_id > 0).map((item) => item.source_symbol_id),
      ...value.prop_substs.filter((item) => item.body_formula_id > 0).map((item) => item.source_symbol_id),
    ])
    if ([...required].some((symbolId) => !completeIds.has(symbolId))) return
    const subst: Substitution = {
      term_substs: value.term_substs.filter((item) => item.target_formula_id > 0),
      prop_substs: value.prop_substs.filter((item) => item.body_formula_id > 0),
    }
    setPending(true)
    try {
      const result = await proofsApi.suggestBackward(proofId, {
        kind: backwardEdit.kind,
        ...(backwardEdit.kind === 'axiom'
          ? { axiom_id: backwardEdit.sourceId }
          : { applied_theorem_id: backwardEdit.sourceId }),
        goal_tokens: findPlanNode(state.root, backwardEdit.holeId)?.goalTokens ?? [],
        subst,
      })
      const candidate = result.candidates.find(
        (item) => item.match_depth === backwardEdit.candidate.match_depth,
      ) ?? result.candidates[0]
      if (candidate == null) throw new Error('変更した代入に一致する backward recipe がありません')
      const choice = { ...backwardEdit }
      dispatch(backwardAction(choice, candidate))
      setBackwardEdit({ ...backwardEdit, candidate, value })
    } catch (error) {
      dispatch({ type: 'failed', holeId: backwardEdit.holeId, message: errorMessage(error) })
    } finally {
      setPending(false)
    }
  }

  async function fillFromPremise(hole: PlanHoleNode, premiseOrd: number): Promise<void> {
    setPending(true)
    try {
      const step = await proofsApi.addStep(proofId, { kind: 'premise', premise_ord: premiseOrd })
      await finishOperation({ type: 'fill', holeId: hole.id, label: `前提 ${premiseOrd}`, stepOrd: step.ord })
      onAdded()
    } catch (error) {
      dispatch({ type: 'failed', holeId: hole.id, message: errorMessage(error) })
    } finally {
      setPending(false)
    }
  }

  async function fillFromEstablished(hole: PlanHoleNode, stepOrd: number): Promise<void> {
    setPending(true)
    try {
      await finishOperation({ type: 'fill', holeId: hole.id, label: `ステップ (${stepOrd}) を再利用`, stepOrd })
    } finally {
      setPending(false)
    }
  }

  async function selectArgument(nodeId: number, premiseIndex: number, stepOrd: number): Promise<void> {
    setPending(true)
    try {
      await finishOperation({ type: 'select_argument', nodeId, premiseIndex, stepOrd })
    } finally {
      setPending(false)
    }
  }

  function implicationBody(hole: PlanHoleNode): Token[] | null {
    const implication = symbols.find((symbol) => symbol.name === '→')
    if (implication == null || hole.assumptionSelection == null) return null
    return implicationBodyForAssumption(
      hole.goalTokens,
      hole.assumptionSelection.tokens,
      implication.id,
      symbolsById,
    )
  }

  async function selectAssumption(hole: PlanHoleNode, formulaId: number): Promise<void> {
    try {
      const formula = await formulasApi.get(formulaId)
      dispatch({ type: 'select_assumption', holeId: hole.id, formulaId, tokens: formula.tokens })
    } catch (error) {
      dispatch({ type: 'failed', holeId: hole.id, message: errorMessage(error) })
    }
  }

  async function discharge(hole: PlanHoleNode): Promise<void> {
    const bodyGoalTokens = implicationBody(hole)
    if (hole.assumptionSelection == null || bodyGoalTokens == null) {
      dispatch({
        type: 'failed', holeId: hole.id,
        message: 'hole の含意の左辺と同じ式を仮定として選んでください',
      })
      return
    }
    setPending(true)
    try {
      const assumption = await proofsApi.addStep(proofId, {
        kind: 'assumption', conclusion_formula_id: hole.assumptionSelection.formulaId,
      })
      await finishOperation({
        type: 'discharge', holeId: hole.id, bodyGoalTokens, assumptionStepOrd: assumption.ord,
      })
      onAdded()
    } catch (error) {
      dispatch({ type: 'failed', holeId: hole.id, message: errorMessage(error) })
    } finally {
      setPending(false)
    }
  }

  function focusAction(selector: string): void {
    editorRef.current?.querySelector<HTMLElement>(selector)?.focus()
  }

  useCommand('plan.hole.next', () => {
    if (!selectedHole || holes.length === 0) return
    const index = holes.findIndex((hole) => hole.id === selectedHole.id)
    setSelectedHoleId(holes[(index + 1) % holes.length].id)
  }, { enabled: holes.length > 1, scope: editorRef })
  useCommand('plan.hole.previous', () => {
    if (!selectedHole || holes.length === 0) return
    const index = holes.findIndex((hole) => hole.id === selectedHole.id)
    setSelectedHoleId(holes[(index - 1 + holes.length) % holes.length].id)
  }, { enabled: holes.length > 1, scope: editorRef })
  useCommand('plan.fill.premise', () => focusAction('[data-plan-fill-premise]'), { enabled: selectedHole != null, scope: editorRef })
  useCommand('plan.fill.step', () => focusAction('[data-plan-fill-step]'), { enabled: selectedHole != null, scope: editorRef })
  useCommand('plan.apply.theorem', () => focusAction('[data-plan-apply-theorem]'), { enabled: selectedHole != null, scope: editorRef })
  useCommand('plan.apply.rule', () => focusAction('[data-testid="plan-rule-picker"] button'), { enabled: showRules && selectedHole != null, scope: editorRef })
  useLayoutEffect(() => {
    if (!showRules) return
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ mode: string; theoremId: number }>).detail
      if (detail.mode !== 'plan' || !selectedHole) return
      const theorem = theorems.find((item) => item.id === detail.theoremId)
      if (theorem) void suggestBackward(selectedHole, 'theorem', theorem)
      else void theoremsApi.get(detail.theoremId).then((item) => suggestBackward(selectedHole, 'theorem', item))
    }
    window.addEventListener('dem:choose-rule', listener)
    return () => window.removeEventListener('dem:choose-rule', listener)
  })
  useCommand('plan.apply.axiom', () => focusAction('[data-plan-apply-axiom]'), { enabled: selectedHole != null, scope: editorRef })
  useCommand('plan.recipe.choose', () => focusAction('[data-plan-recipe]'), { enabled: backwardChoice != null, scope: editorRef })
  useCommand('plan.assume', () => focusAction('[data-plan-assume]'), { enabled: selectedHole != null, scope: editorRef })
  useCommand('plan.argument.choose', () => focusAction('[data-plan-argument]'), { scope: editorRef })

  return (
    <div ref={editorRef} data-top-down data-rule-enabled={showRules} className="rounded-lg border border-violet-200 bg-violet-50/40 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-violet-950">目標から組み立てる</h3>
          <p className="mt-1 text-xs text-violet-800">補題を先に選び、開いた hole を埋めると依存順に step を追加します。</p>
        </div>
        <span ref={planStatusRef} tabIndex={-1} className="rounded bg-white px-2 py-1 text-xs text-violet-800">
          {isProofPlanComplete(state) ? 'plan 完成' : `未達成 ${holes.length}`}
        </span>
      </div>

      <div className="mt-3 rounded border border-violet-100 bg-white p-3">
        <PlanNodeView
          node={state.root}
          symbolsById={symbolsById}
          selectedHoleId={selectedHole?.id ?? null}
          pending={pending}
          onSelect={setSelectedHoleId}
          onSelectArgument={(nodeId, premiseIndex, stepOrd) => {
            void selectArgument(nodeId, premiseIndex, stepOrd)
          }}
        />
      </div>

      {backwardChoice && (
        <div className="mt-3 space-y-2 rounded border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-semibold text-amber-900">backward recipe を選択</p>
          {backwardChoice.candidates.map((candidate, index) => (
            <button
              key={`${candidate.match_depth}-${index}`}
              type="button"
              data-plan-recipe
              disabled={pending}
              onClick={() => void acceptBackwardCandidate(backwardChoice, candidate)}
              className="mr-2 rounded bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
            >
              {candidate.match_depth === 0 ? 'MP なし' : `MP ${candidate.match_depth} 回`}
            </button>
          ))}
        </div>
      )}

      {backwardEdit && (
        <div className="mt-3 space-y-2 rounded border border-indigo-200 bg-indigo-50 p-3">
          <p className="text-xs font-semibold text-indigo-900">backward substitution</p>
          {(backwardEdit.candidate.subst.term_substs.length
            + backwardEdit.candidate.subst.prop_substs.length) > 0 && (
            <p className="text-xs text-indigo-800">
              自動決定: {[...backwardEdit.candidate.subst.term_substs, ...backwardEdit.candidate.subst.prop_substs]
                .map((item) => `#${item.source_symbol_id}`).join(', ')}
            </p>
          )}
          {backwardEdit.candidate.defaulted_to_identity.length > 0 && (
            <p className="text-xs text-indigo-800">
              既定（恒等、変更可）: {backwardEdit.candidate.defaulted_to_identity.map((id) => `#${id}`).join(', ')}
            </p>
          )}
          {backwardEdit.candidate.undetermined.length > 0 && (
            <p className="text-xs text-amber-700">
              必須入力: {backwardEdit.candidate.undetermined.map((item) => item.name).join(', ')}
            </p>
          )}
          <SubstitutionEditor
            value={backwardEdit.value}
            onChange={(value) => void updateBackwardSubstitution(value)}
            editableSymbolIds={[
              ...backwardEdit.candidate.defaulted_to_identity,
              ...backwardEdit.candidate.undetermined.map((item) => item.symbol_id),
            ]}
            context={context}
          />
        </div>
      )}

      {backwardRequiredIncomplete && (
        <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          必須の代入を入力すると hole の編集を続けられます。
        </p>
      )}

      {selectedHole && !backwardRequiredIncomplete && (
        <div ref={actionPanelRef} data-hole-actions={selectedHole.id} className="mt-3 space-y-3 rounded border border-violet-100 bg-white p-3">
          <div>
            <p className="text-xs font-semibold text-violet-900">hole #{selectedHole.id} の goal</p>
            <PlanFormula tokens={selectedHole.goalTokens} symbolsById={symbolsById} />
          </div>

          <div className="flex flex-wrap gap-2">
            {proofState.premises.filter((premise) => sameTokens(premise.tokens, selectedHole.goalTokens)).map((premise) => (
              <button data-plan-fill-premise key={`premise-${premise.ord}`} type="button" disabled={pending} onClick={() => void fillFromPremise(selectedHole, premise.ord)} className="rounded bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
                前提 {premise.ord} で埋める
              </button>
            ))}
            {proofState.established.filter((step) => sameTokens(step.tokens, selectedHole.goalTokens)).map((step) => (
              <button data-plan-fill-step key={`step-${step.ord}`} type="button" disabled={pending} onClick={() => void fillFromEstablished(selectedHole, step.ord)} className="rounded bg-slate-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
                step ({step.ord}) を再利用
              </button>
            ))}
          </div>

          <label className="block text-xs text-slate-600">
            補題を適用
            <select data-plan-apply-theorem value="" disabled={pending} onChange={(event) => {
              const theorem = theorems.find((item) => item.id === Number(event.target.value))
              if (theorem) void suggestBackward(selectedHole, 'theorem', theorem)
            }} className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm">
              <option value="" disabled>補題を選択…</option>
              {theorems.map((theorem) => <option key={theorem.id} value={theorem.id}>{theorem.name}</option>)}
            </select>
          </label>
          {showRules && <div>
            <p className="mb-1 text-xs text-slate-600">推論定理を適用</p>
            <InferenceRulePicker testId="plan-rule-picker" onChoose={(theorem) => void suggestBackward(selectedHole, 'theorem', theorem)} />
          </div>}

          <label className="block text-xs text-slate-600">
            公理を適用
            <select data-plan-apply-axiom value="" disabled={pending} onChange={(event) => {
              const axiom = axioms.find((item) => item.id === Number(event.target.value))
              if (axiom) void suggestBackward(selectedHole, 'axiom', axiom)
            }} className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm">
              <option value="" disabled>公理を選択…</option>
              {axioms.map((axiom) => <option key={axiom.id} value={axiom.id}>{axiom.name}</option>)}
            </select>
          </label>

          <details className="rounded border border-slate-200 p-2">
            <summary data-plan-assume className="cursor-pointer text-xs font-semibold text-slate-700">含意を仮定して証明する（⇒導入）</summary>
            <div className="mt-2 space-y-2">
              <FormulaPicker value={selectedHole.assumptionSelection?.formulaId ?? null} onChange={(formulaId) => void selectAssumption(selectedHole, formulaId)} context={context} />
              <button type="button" disabled={pending || implicationBody(selectedHole) == null} onClick={() => void discharge(selectedHole)} className="rounded bg-violet-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40">
                この仮定を置く
              </button>
            </div>
          </details>

          {selectedHole.error && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">hole #{selectedHole.id}: {selectedHole.error}</p>}
        </div>
      )}
      {state.root.error && state.root.kind !== 'hole' && (
        <p className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">plan node #{state.root.id}: {state.root.error}</p>
      )}
    </div>
  )
}

function PlanFormula({ tokens, symbolsById }: { tokens: Token[]; symbolsById: Map<number, Symbol> }) {
  const tree = tokensToTree(tokens, symbolsById).tree
  return tree
    ? <Latex>{renderLatex(tree, symbolsById)}</Latex>
    : <span className="text-red-700">この式は木で表示できません</span>
}

function PlanNodeView({
  node,
  symbolsById,
  selectedHoleId,
  pending,
  onSelect,
  onSelectArgument,
}: {
  node: ProofPlanNode
  symbolsById: Map<number, Symbol>
  selectedHoleId: number | null
  pending: boolean
  onSelect: (id: number) => void
  onSelectArgument: (nodeId: number, premiseIndex: number, stepOrd: number) => void
}) {
  const children = node.kind === 'plan'
    ? node.application.kind === 'mp' ? [node.premises[1], node.premises[0]] : node.premises
    : node.kind === 'discharge' ? [node.body] : []
  const label = node.kind === 'hole'
    ? '未達成 hole'
    : node.kind === 'filled'
      ? `${node.label} → step (${node.stepOrd})`
      : node.kind === 'plan'
        ? `${node.application.label}${node.stepOrd == null ? ' (plan)' : ` → step (${node.stepOrd})`}`
        : `⇒導入: 仮定 step (${node.assumptionStepOrd}) を解消${node.stepOrd == null ? '' : ` → step (${node.stepOrd})`}`
  return (
    <div className="border-l border-violet-200 pl-3">
      <button type="button" disabled={node.kind !== 'hole'} onClick={() => onSelect(node.id)} className={`text-left text-xs ${node.kind === 'hole' ? 'font-semibold text-violet-700' : 'text-slate-600'} ${selectedHoleId === node.id ? 'underline' : ''}`}>
        {label}
      </button>
      <div className="mt-0.5 text-sm"><PlanFormula tokens={node.goalTokens} symbolsById={symbolsById} /></div>
      {node.kind === 'plan' && node.argumentCandidates.map((candidates, premiseIndex) => (
        candidates.length >= 2 && (
          <label key={`argument-${premiseIndex}`} className="mt-1 block text-xs text-slate-600">
            引数 {premiseIndex + 1}
            <select
              data-plan-argument
              value={node.argumentSelections[premiseIndex] ?? ''}
              disabled={pending || node.stepOrd !== null}
              onChange={(event) => onSelectArgument(node.id, premiseIndex, Number(event.target.value))}
              className="ml-2 rounded border border-slate-300 px-2 py-1"
            >
              <option value="" disabled>候補から選択…</option>
              {candidates.map((stepOrd) => (
                <option key={stepOrd} value={stepOrd}>step ({stepOrd})</option>
              ))}
            </select>
          </label>
        )
      ))}
      {node.kind === 'plan'
        && (node.application.kind === 'axiom' || node.application.kind === 'theorem')
        && (node.application.subst.term_substs.length + node.application.subst.prop_substs.length > 0) && (
        <p className="mt-1 text-xs text-slate-500">
          代入: {[
            ...node.application.subst.term_substs.map(
              (item) => `#${item.source_symbol_id} ↦ formula #${item.target_formula_id}`,
            ),
            ...node.application.subst.prop_substs.map(
              (item) => `#${item.source_symbol_id} ↦ formula #${item.body_formula_id}`,
            ),
          ].join(', ')}
        </p>
      )}
      {node.error && <p className="text-xs text-red-700">hole/node #{node.id}: {node.error}</p>}
      {children.length > 0 && (
        <div className="mt-2 space-y-2">
          {children.map((child) => (
            <PlanNodeView
              key={child.id}
              node={child}
              symbolsById={symbolsById}
              selectedHoleId={selectedHoleId}
              pending={pending}
              onSelect={onSelect}
              onSelectArgument={onSelectArgument}
            />
          ))}
        </div>
      )}
    </div>
  )
}
