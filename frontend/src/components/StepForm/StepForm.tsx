import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { proofsApi } from '../../api/proofs'
import { theoremsApi } from '../../api/theorems'
import { axiomsApi } from '../../api/axioms'
import { symbolsApi } from '../../api/symbols'
import { formulasApi } from '../../api/formulas'
import { FormulaPicker } from '../FormulaPicker'
import { SubstitutionEditor } from './SubstitutionEditor'
import { ApiError } from '../../api/client'
import type { ProofStep, ProofStepCreate, StepKind, StepSuggestion, Substitution, Token } from '../../api/types'
import { emptySubstitution } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'
import { Latex } from '../Latex'
import { renderLatex, tokensToTree } from '../FormulaEditor/model'
import { useCommand } from '../../commands/CommandProvider'
import { InferenceRulePicker } from '../InferenceRulePicker'
import { FormulaPreview } from '../FormulaPreview'

interface StepFormProps {
  proofId: number
  theoremId: number
  priorSteps: ProofStep[]
  onAdded: () => void
  context?: Record<string, number>
  initialRuleStepOrd?: number | null
  showRules?: boolean
}

const COMMANDS: { kind: StepKind; label: string }[] = [
  { kind: 'premise', label: '前提を使う' },
  { kind: 'assumption', label: '仮定する' },
  { kind: 'axiom', label: '公理を使う' },
  { kind: 'theorem', label: '補題を使う' },
  { kind: 'mp', label: '含意から導く' },
  { kind: 'gen', label: '任意の変数に広げる' },
  { kind: 'imp_intro', label: '仮定を閉じる' },
]

export function StepForm({ proofId, theoremId, priorSteps, onAdded, context = {}, initialRuleStepOrd = null, showRules = true }: StepFormProps) {
  const formRef = useRef<HTMLDivElement>(null)
  const [kind, setKind] = useState<StepKind>('premise')
  const [ruleMode, setRuleMode] = useState(false)
  const [assumptionConclusionId, setAssumptionConclusionId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [premiseOrd, setPremiseOrd] = useState<number | ''>('')
  const [axiomId, setAxiomId] = useState<number | ''>('')
  const [appliedTheoremId, setAppliedTheoremId] = useState<number | ''>('')
  const [appliedProofId, setAppliedProofId] = useState<number | ''>('')
  const [argStepOrds, setArgStepOrds] = useState<number[]>([])
  const [antecedentOrd, setAntecedentOrd] = useState<number | ''>('')
  const [implicationOrd, setImplicationOrd] = useState<number | ''>('')
  const [bodyOrd, setBodyOrd] = useState<number | ''>('')
  const [assumptionOrd, setAssumptionOrd] = useState<number | ''>('')
  const [genVarId, setGenVarId] = useState<number | ''>('')
  const [subst, setSubst] = useState<Substitution>(emptySubstitution)
  const [suggestion, setSuggestion] = useState<StepSuggestion | null>(null)
  const [lemmaSearch, setLemmaSearch] = useState('')
  const [lemmaGoalFormulaId, setLemmaGoalFormulaId] = useState<number | null>(null)
  const [candidateArgStepOrds, setCandidateArgStepOrds] = useState<number[]>([])

  const { data: premises = [] } = useQuery({
    queryKey: ['theorems', theoremId, 'premises'],
    queryFn: () => theoremsApi.listPremises(theoremId),
  })
  const { data: provenTheorems = [] } = useQuery({
    queryKey: ['theorems', 'lemma-picker'],
    queryFn: () => theoremsApi.listVisible({ status: 'proven' }),
  })
  const { data: axioms = [] } = useQuery({ queryKey: ['axioms'], queryFn: () => axiomsApi.list() })
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols() })
  const { data: lemmaGoalFormula } = useQuery({
    queryKey: ['formulas', lemmaGoalFormulaId],
    queryFn: () => formulasApi.get(Number(lemmaGoalFormulaId)),
    enabled: lemmaGoalFormulaId != null,
  })
  const hasLemmaConstraints = lemmaGoalFormulaId != null || candidateArgStepOrds.length > 0
  const { data: applicableTheorems = [], isFetching: applicableFetching } = useQuery({
    queryKey: ['theorems', 'applicable', proofId, lemmaGoalFormulaId, candidateArgStepOrds],
    queryFn: () => theoremsApi.listApplicable({
      goalFormulaId: lemmaGoalFormulaId,
      proofId,
      argStepOrds: candidateArgStepOrds,
    }),
    enabled: kind === 'theorem' && hasLemmaConstraints,
  })
  const termVars = useMemo(
    () => symbols.filter((symbol) => symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable),
    [symbols],
  )
  const symbolsById = useMemo(
    () => new Map(symbols.map((symbol) => [symbol.id, symbol])),
    [symbols],
  )
  const suggestedConclusionLatex = useMemo(() => {
    if (!suggestion?.conclusion_tokens) return null
    const tree = tokensToTree(suggestion.conclusion_tokens, symbolsById).tree
    return tree ? renderLatex(tree, symbolsById) : null
  }, [suggestion, symbolsById])
  const lemmaOptions = useMemo(() => {
    const needle = lemmaSearch.trim().toLocaleLowerCase()
    return provenTheorems
      .filter((item) => !needle || item.name.toLocaleLowerCase().includes(needle))
      .slice(0, 100)
  }, [lemmaSearch, provenTheorems])
  const concreteApplicable = applicableTheorems.filter((item) => !item.is_schematic)
  const schematicApplicable = applicableTheorems.filter((item) => item.is_schematic)

  const suggestMutation = useMutation({
    mutationFn: (request:
      | { kind: 'theorem'; applied_theorem_id: number; arg_step_ords?: number[]; goal_tokens?: Token[] }
      | { kind: 'axiom'; axiom_id: number }) =>
      proofsApi.suggestStep(proofId, request),
    onSuccess: (result, request) => {
      setSuggestion(result)
      const nextSubst: Substitution = {
        term_substs: [...result.subst.term_substs],
        prop_substs: [...result.subst.prop_substs],
      }
      for (const item of result.undetermined) {
        const symbol = symbols.find((candidate) => candidate.id === item.symbol_id)
        if (symbol?.symbol_type.name === SYMBOL_TYPE.freeTermVariable) {
          if (!nextSubst.term_substs.some((substItem) => substItem.source_symbol_id === symbol.id)) {
            nextSubst.term_substs.push({ source_symbol_id: symbol.id, target_formula_id: 0 })
          }
        } else if (symbol?.symbol_type.name === SYMBOL_TYPE.freePropositionVariable) {
          if (!nextSubst.prop_substs.some((substItem) => substItem.source_symbol_id === symbol.id)) {
            nextSubst.prop_substs.push({
              source_symbol_id: symbol.id,
              body_formula_id: 0,
              formal_param_symbol_ids: Array.from(
                { length: symbol.arity },
                (_, index) => termVars[index]?.id ?? termVars[0]?.id ?? 0,
              ),
            })
          }
        }
      }
      setSubst(nextSubst)
      if (result.applied_proof_id != null) setAppliedProofId(result.applied_proof_id)
      if (ruleMode && request.kind === 'theorem') {
        const matchingSlot = result.arg_candidates.findIndex((candidates) => initialRuleStepOrd != null && candidates.includes(initialRuleStepOrd))
        const next = request.arg_step_ords?.length === result.premise_count
          ? request.arg_step_ords
          : Array.from({ length: result.premise_count }, (_, index) => {
              const candidates = result.arg_candidates[index] ?? []
              if (index === matchingSlot && initialRuleStepOrd != null) return initialRuleStepOrd
              return candidates.length === 1 ? candidates[0] : -1
            })
        setArgStepOrds(next)
        if (request.arg_step_ords?.length !== result.premise_count && next.every((ord) => ord >= 0)) {
          suggestMutation.mutate({ kind: 'theorem', applied_theorem_id: request.applied_theorem_id, arg_step_ords: next })
        }
      } else {
        setArgStepOrds(
          request.kind === 'theorem' && request.arg_step_ords?.length === result.premise_count
            ? request.arg_step_ords
            : Array.from({ length: result.premise_count }, (_, index) =>
                result.arg_candidates[index]?.[0] ?? priorSteps[0]?.ord ?? 0,
              ),
        )
      }
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : '候補を計算できませんでした'),
  })

  useEffect(() => {
    setSuggestion(null)
    setSubst(emptySubstitution)
  }, [kind])

  useEffect(() => {
    setAppliedTheoremId('')
    setAppliedProofId('')
    setSuggestion(null)
    setSubst(emptySubstitution)
    setArgStepOrds([])
  }, [lemmaGoalFormulaId, candidateArgStepOrds])

  function chooseLemma(theoremId: number, asRule = ruleMode) {
    setAppliedTheoremId(theoremId)
    suggestMutation.mutate({
      kind: 'theorem',
      applied_theorem_id: theoremId,
      arg_step_ords: asRule ? [] : candidateArgStepOrds,
      goal_tokens: asRule ? undefined : lemmaGoalFormula?.tokens,
    })
  }

  useEffect(() => {
    if (initialRuleStepOrd == null) return
    setKind('theorem')
    setRuleMode(true)
    setCandidateArgStepOrds([initialRuleStepOrd])
    formRef.current?.scrollIntoView({ block: 'nearest' })
  }, [initialRuleStepOrd])

  function toggleCandidateArgument(ord: number) {
    setCandidateArgStepOrds((current) => (
      current.includes(ord)
        ? current.filter((item) => item !== ord)
        : priorSteps.filter((step) => current.includes(step.ord) || step.ord === ord).map((step) => step.ord)
    ))
  }

  const addStepMutation = useMutation({
    mutationFn: (body: ProofStepCreate) => proofsApi.addStep(proofId, body),
    onSuccess: () => {
      onAdded()
      setAssumptionConclusionId(null)
      setArgStepOrds([])
      setCandidateArgStepOrds([])
      setSubst(emptySubstitution)
      setSuggestion(null)
      setError(null)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'ステップを追加できませんでした'),
  })

  function buildStepInput(): ProofStepCreate | null {
    switch (kind) {
      case 'premise':
        return premiseOrd === '' ? null : { kind, premise_ord: premiseOrd }
      case 'assumption':
        return assumptionConclusionId == null
          ? null
          : { kind, conclusion_formula_id: assumptionConclusionId }
      case 'axiom':
        return axiomId === '' ? null : { kind, axiom_id: axiomId, subst }
      case 'theorem':
        return appliedProofId === '' ? null : {
          kind,
          applied_proof_id: appliedProofId,
          subst,
          arg_step_ords: argStepOrds,
        }
      case 'mp':
        return antecedentOrd === '' || implicationOrd === '' ? null : {
          kind,
          antecedent_step_ord: antecedentOrd,
          implication_step_ord: implicationOrd,
        }
      case 'gen':
        return bodyOrd === '' || genVarId === '' ? null : {
          kind,
          body_step_ord: bodyOrd,
          gen_variable_symbol_id: genVarId,
        }
      case 'imp_intro':
        return assumptionOrd === '' || bodyOrd === '' ? null : {
          kind,
          assumption_step_ord: assumptionOrd,
          body_step_ord: bodyOrd,
        }
    }
  }

  const stepInput = buildStepInput()
  const substitutionComplete = subst.term_substs.every((item) => item.target_formula_id > 0)
    && subst.prop_substs.every(
      (item) => item.body_formula_id > 0 && item.formal_param_symbol_ids.every((id) => id > 0),
    )
  const commitEnabled = stepInput != null && substitutionComplete
    && (!ruleMode || kind !== 'theorem' || (suggestion != null && argStepOrds.length === suggestion.premise_count && argStepOrds.every((ord) => ord >= 0)))
    && !addStepMutation.isPending && !suggestMutation.isPending
  const runCommit = useCommand('step.commit', () => {
    if (stepInput) addStepMutation.mutate(stepInput)
  }, { enabled: commitEnabled, scope: formRef })
  useCommand('step.add.premise', () => setKind('premise'), { scope: formRef })
  useCommand('step.add.assumption', () => setKind('assumption'), { scope: formRef })
  useCommand('step.add.axiom', () => setKind('axiom'), { scope: formRef })
  useCommand('step.add.theorem', () => setKind('theorem'), { scope: formRef })
  useCommand('step.apply.rule', () => {
    setKind('theorem')
    setRuleMode(true)
    formRef.current?.querySelector<HTMLElement>('[data-testid="step-rule-picker"] button')?.focus()
  }, { enabled: showRules, scope: formRef })
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ mode: string; theoremId: number }>).detail
      if (detail.mode !== 'step' || !showRules) return
      setKind('theorem')
      setRuleMode(true)
      chooseLemma(detail.theoremId, true)
      formRef.current?.scrollIntoView({ block: 'nearest' })
    }
    window.addEventListener('dem:choose-rule', listener)
    return () => window.removeEventListener('dem:choose-rule', listener)
  })
  useCommand('step.add.mp', () => setKind('mp'), { scope: formRef })
  useCommand('step.add.gen', () => setKind('gen'), { scope: formRef })
  useCommand('step.add.imp-intro', () => setKind('imp_intro'), { scope: formRef })
  const priorOptions = (value: number | '', change: (value: number) => void) => (
    <select
      value={value}
      onChange={(event) => change(Number(event.target.value))}
      className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
    >
      <option value="" disabled>選択…</option>
      {priorSteps.map((step) => <option key={step.ord} value={step.ord}>#{step.ord}</option>)}
    </select>
  )

  return (
    <div ref={formRef} data-step-form data-rule-enabled={showRules} className="space-y-4 rounded-lg border border-slate-200 p-4">
      <div>
        <div className="mb-2 text-xs font-medium text-slate-500">何をしますか？</div>
        <div className="flex flex-wrap gap-2">
          {COMMANDS.map((command) => (
            <button
              key={command.kind}
              type="button"
              onClick={() => { setKind(command.kind); setRuleMode(false) }}
              className={`rounded px-3 py-1.5 text-xs ${kind === command.kind ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
            >
              {command.label}
            </button>
          ))}
          {showRules && <button type="button" onClick={() => { setKind('theorem'); setRuleMode(true) }} className={`rounded px-3 py-1.5 text-xs ${kind === 'theorem' && ruleMode ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>推論定理を使う</button>}
        </div>
      </div>

      {kind === 'premise' && (
        <label className="block text-xs text-slate-500">
          使う前提
          <select
            value={premiseOrd}
            onChange={(event) => setPremiseOrd(Number(event.target.value))}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>選択…</option>
            {premises.map((premise) => (
              <option key={premise.ord} value={premise.ord}>前提 {premise.ord + 1}（式 #{premise.formula.id}）</option>
            ))}
          </select>
        </label>
      )}

      {kind === 'axiom' && (
        <label className="block text-xs text-slate-500">
          使う公理
          <select
            value={axiomId}
            onChange={(event) => {
              const id = Number(event.target.value)
              setAxiomId(id)
              suggestMutation.mutate({ kind: 'axiom', axiom_id: id })
            }}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>選択…</option>
            {axioms.map((axiom) => <option key={axiom.id} value={axiom.id}>{axiom.name}</option>)}
          </select>
        </label>
      )}

      {kind === 'theorem' && (
        <div className="space-y-3">
          {ruleMode && <InferenceRulePicker testId="step-rule-picker" selectedId={appliedTheoremId} onChoose={(theorem) => chooseLemma(theorem.id)} />}
          {!ruleMode && <>
          <div className="rounded border border-indigo-100 bg-indigo-50 p-3">
            <div className="text-xs font-medium text-indigo-900">補題候補を絞り込む</div>
            <div className="mt-2 text-xs text-slate-600">先に使いたいステップを選ぶ</div>
            <div className="mt-1 flex flex-wrap gap-2">
              {priorSteps.map((step) => (
                <label key={step.ord} className="rounded bg-white px-2 py-1 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={candidateArgStepOrds.includes(step.ord)}
                    onChange={() => toggleCandidateArgument(step.ord)}
                    className="mr-1"
                  />
                  #{step.ord}
                </label>
              ))}
              {priorSteps.length === 0 && <span className="text-xs text-slate-400">利用できるステップはまだありません</span>}
            </div>
            <div className="mt-3 text-xs text-slate-600">または、次に示したい式を書く</div>
            <div className="mt-1 rounded bg-white p-2">
              <FormulaPicker value={lemmaGoalFormulaId} onChange={setLemmaGoalFormulaId} context={context} />
            </div>
          </div>

          {hasLemmaConstraints && (
            <div className="rounded border border-slate-200 p-3">
              <div className="text-xs font-medium text-slate-700">
                おすすめの補題 {applicableFetching ? '（計算中…）' : `（${applicableTheorems.length} 件）`}
              </div>
              <div className="mt-2 space-y-1">
                {concreteApplicable.map((item) => (
                  <button
                    key={item.theorem.id}
                    type="button"
                    disabled={lemmaGoalFormulaId != null && lemmaGoalFormula == null}
                    onClick={() => chooseLemma(item.theorem.id)}
                    className="block w-full rounded px-2 py-1 text-left text-sm text-slate-700 hover:bg-indigo-50 disabled:opacity-40"
                  >
                    {item.theorem.name}
                  </button>
                ))}
              </div>
              {schematicApplicable.length > 0 && (
                <details className="mt-2 text-xs text-slate-600">
                  <summary className="cursor-pointer">汎用補題（{schematicApplicable.length} 件）</summary>
                  <div className="mt-1 space-y-1 pl-2">
                    {schematicApplicable.map((item) => (
                      <button
                        key={item.theorem.id}
                        type="button"
                        disabled={lemmaGoalFormulaId != null && lemmaGoalFormula == null}
                        onClick={() => chooseLemma(item.theorem.id)}
                        className="block w-full rounded px-2 py-1 text-left hover:bg-indigo-50 disabled:opacity-40"
                      >
                        {item.theorem.name}
                      </button>
                    ))}
                  </div>
                </details>
              )}
              {!applicableFetching && applicableTheorems.length === 0 && (
                <p className="mt-2 text-xs text-slate-500">候補がありません。下の定理名検索を使えます。</p>
              )}
            </div>
          )}

          <label className="block text-xs text-slate-500">
            定理名で検索
            <input
              value={lemmaSearch}
              onChange={(event) => setLemmaSearch(event.target.value)}
              placeholder="定理名で絞り込み"
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <select
              value={appliedTheoremId}
              onChange={(event) => {
                const id = Number(event.target.value)
                chooseLemma(id)
              }}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>選択…</option>
              {lemmaOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          </>}
          {suggestion && Array.from({ length: suggestion.premise_count }, (_, index) => (
            <div key={index} className="block text-xs text-slate-500">
              <label>
              前提 {index + 1} に使うステップ
              <select
                value={argStepOrds[index] ?? ''}
                onChange={(event) => {
                  const next = [...argStepOrds]
                  next[index] = Number(event.target.value)
                  setArgStepOrds(next)
                  if (appliedTheoremId !== '' && (!ruleMode || next.every((ord) => ord >= 0))) {
                    suggestMutation.mutate({
                      kind: 'theorem',
                      applied_theorem_id: appliedTheoremId,
                      arg_step_ords: next,
                      goal_tokens: ruleMode ? undefined : lemmaGoalFormula?.tokens,
                    })
                  }
                }}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              >
                {ruleMode && <option value={-1} disabled>候補が複数あります。式を確認して選択…</option>}
                {(suggestion.arg_candidates[index]?.length
                  ? suggestion.arg_candidates[index]
                  : ruleMode ? [] : priorSteps.map((step) => step.ord)
                ).map((ord) => <option key={ord} value={ord}>#{ord}{ruleMode ? ` — ${priorSteps.find((step) => step.ord === ord)?.conclusion_formula.description ?? '一致候補'}` : ''}</option>)}
              </select>
              </label>
              {ruleMode && (suggestion.arg_candidates[index]?.length ?? 0) > 1 && <p className="mt-1 text-amber-700">複数の step がこの前提の式に一致します。使う step を選んでください。</p>}
              {ruleMode && <div className="mt-1 space-y-1">
                {(suggestion.arg_candidates[index] ?? []).map((ord) => {
                  const step = priorSteps.find((item) => item.ord === ord)
                  return step && <div key={ord}>step ({ord}): <FormulaPreview formulaId={step.conclusion_formula.id} /></div>
                })}
              </div>}
            </div>
          ))}
        </div>
      )}

      {kind === 'mp' && (
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">前件 φ{priorOptions(antecedentOrd, setAntecedentOrd)}</label>
          <label className="text-xs text-slate-500">含意 φ→ψ{priorOptions(implicationOrd, setImplicationOrd)}</label>
        </div>
      )}

      {kind === 'gen' && (
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">広げる式{priorOptions(bodyOrd, setBodyOrd)}</label>
          <label className="text-xs text-slate-500">
            変数
            <select
              value={genVarId}
              onChange={(event) => setGenVarId(Number(event.target.value))}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>選択…</option>
              {termVars.map((symbol) => <option key={symbol.id} value={symbol.id}>{symbol.name}</option>)}
            </select>
          </label>
        </div>
      )}

      {kind === 'imp_intro' && (
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">
            閉じる仮定
            <select
              value={assumptionOrd}
              onChange={(event) => setAssumptionOrd(Number(event.target.value))}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>選択…</option>
              {priorSteps.filter((step) => step.step_kind === 'assumption').map((step) => (
                <option key={step.ord} value={step.ord}>#{step.ord}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">仮定の下で得た式{priorOptions(bodyOrd, setBodyOrd)}</label>
        </div>
      )}

      {kind === 'assumption' && (
        <div>
          <div className="mb-1 text-xs text-slate-500">仮定する式</div>
          <FormulaPicker value={assumptionConclusionId} onChange={setAssumptionConclusionId} context={context} />
        </div>
      )}

      {suggestion && (
        <div className="rounded bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
          {suggestion.defaulted_to_identity.length + suggestion.subst.term_substs.length + suggestion.subst.prop_substs.length + suggestion.undetermined.length} 件中
          {' '}{suggestion.defaulted_to_identity.length + suggestion.subst.term_substs.length + suggestion.subst.prop_substs.length} 件を自動決定
        </div>
      )}
      {suggestedConclusionLatex && (
        <div className="rounded border border-indigo-100 bg-white px-3 py-2">
          <div className="mb-1 text-xs text-slate-500">追加される結論</div>
          <Latex display>{suggestedConclusionLatex}</Latex>
        </div>
      )}
      {suggestion && suggestion.undetermined.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-amber-700">決められなかった変数だけ入力してください。</p>
          <SubstitutionEditor
            value={subst}
            onChange={setSubst}
            editableSymbolIds={suggestion.undetermined.map((item) => item.symbol_id)}
            context={context}
          />
        </div>
      )}

      <button
        type="button"
        disabled={!commitEnabled}
        onClick={() => runCommit()}
        className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
      >
        このステップを追加 <kbd aria-hidden="true" className="ml-1 text-xs">Ctrl/⌘ Enter</kbd>
      </button>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
