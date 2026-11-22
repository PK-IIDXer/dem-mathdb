import { useDisplayError } from "../../i18n/useDisplayError"
import { useLanguage } from "../../i18n/useLanguage"
import { t } from "../../i18n/translate"
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { proofsApi } from '../../api/proofs'
import { theoremsApi } from '../../api/theorems'
import { axiomsApi } from '../../api/axioms'
import { symbolsApi } from '../../api/symbols'
import { formulasApi } from '../../api/formulas'
import { FormulaPicker } from '../FormulaPicker'
import { SubstitutionEditor } from './SubstitutionEditor'
import { completedSubstitution, createSubstitutionDraft, type SubstitutionDraft } from './substitutionDraft'
import { ArgumentMismatchMessage } from './ArgumentMismatchMessage'
import { argumentMismatch, type ArgumentMismatch } from './argumentMismatch'
import { ApiError } from '../../api/client'
import type { ProofStep, ProofStepCreate, StepKind, StepSuggestion, Theorem, Token } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'
import { Latex } from '../Latex'
import { renderLatex, renderPreview, tokensToTree } from '../FormulaEditor/model'
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

type SuggestionRequest =
  | { kind: 'theorem'; applied_theorem_id: number; arg_step_ords?: number[]; goal_tokens?: Token[]; keepSlots?: boolean }
  | { kind: 'axiom'; axiom_id: number }

const COMMANDS: { kind: StepKind; label: string }[] = [
  { kind: 'premise', get label() { return t("StepForm_372") } },
  { kind: 'assumption', get label() { return t("StepForm_373") } },
  { kind: 'axiom', get label() { return t("StepForm_374") } },
  { kind: 'theorem', get label() { return t("StepForm_375") } },
  { kind: 'mp', get label() { return t("StepForm_376") } },
  { kind: 'gen', get label() { return t("StepForm_377") } },
  { kind: 'imp_intro', get label() { return t("StepForm_378") } },
]

export function StepForm({ proofId, theoremId, priorSteps, onAdded, context = {}, initialRuleStepOrd = null, showRules = true }: StepFormProps) {
  useLanguage()

  const formRef = useRef<HTMLDivElement>(null)
  const latestSuggestion = useRef<SuggestionRequest | null>(null)
  const [kind, setKind] = useState<StepKind>('premise')
  const [ruleMode, setRuleMode] = useState(false)
  const [assumptionConclusionId, setAssumptionConclusionId] = useState<number | null>(null)
  const [error, setError] = useDisplayError()
  const [premiseOrd, setPremiseOrd] = useState<number | ''>('')
  const [axiomId, setAxiomId] = useState<number | ''>('')
  const [appliedTheoremId, setAppliedTheoremId] = useState<number | ''>('')
  const [argStepOrds, setArgStepOrds] = useState<number[]>([])
  const [antecedentOrd, setAntecedentOrd] = useState<number | ''>('')
  const [implicationOrd, setImplicationOrd] = useState<number | ''>('')
  const [bodyOrd, setBodyOrd] = useState<number | ''>('')
  const [assumptionOrd, setAssumptionOrd] = useState<number | ''>('')
  const [genVarId, setGenVarId] = useState<number | ''>('')
  const [editedDraft, setEditedDraft] = useState<SubstitutionDraft | null>(null)
  const [mismatch, setMismatch] = useState<ArgumentMismatch | null>(null)
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
  const { data: proofState } = useQuery({
    queryKey: ['proofs', proofId, 'state'],
    queryFn: () => proofsApi.getState(proofId),
    enabled: kind === 'axiom' || kind === 'theorem',
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
  const inferredDraft = useMemo(() => suggestion && createSubstitutionDraft(suggestion, symbols, [
    suggestion.conclusion_tokens ?? [],
    lemmaGoalFormula?.tokens ?? [],
    proofState?.goal_tokens ?? [],
    ...(proofState?.established.map((step) => step.tokens) ?? []),
  ]), [suggestion, symbols, lemmaGoalFormula, proofState])
  const draft = editedDraft ?? inferredDraft
  const subst = suggestion && draft && completedSubstitution(suggestion, draft, symbolsById)
  // The candidate lists describe the inferred values. Edits may change the
  // premises, so an edited draft cannot reuse the exact-match labels.
  const changedSubstitution = editedDraft != null && (subst == null || (
    suggestion != null && JSON.stringify(subst) !== JSON.stringify(suggestion.subst)
  ))
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
  function tooFewPremises(theorem: Theorem) {
    return theorem.premise_formula_ids.length < candidateArgStepOrds.length
  }

  const concreteApplicable = applicableTheorems.filter((item) => !item.is_schematic)
  const schematicApplicable = applicableTheorems.filter((item) => item.is_schematic)

  const suggestMutation = useMutation({
    mutationFn: (request: SuggestionRequest) =>
      proofsApi.suggestStep(proofId, request.kind === 'theorem'
        ? { kind: request.kind, applied_theorem_id: request.applied_theorem_id, arg_step_ords: request.arg_step_ords, goal_tokens: request.goal_tokens }
        : request),
    onSuccess: (result, request) => {
      if (latestSuggestion.current !== request) return
      const selected = request.kind === 'theorem' ? request.arg_step_ords ?? [] : []
      if (request.kind === 'theorem' && request.keepSlots && (result.arg_slots.length !== selected.length || result.arg_slots.some((slot, index) => slot !== index))) return
      setSuggestion(result)
      setEditedDraft(null)
      setError(null)
      if (request.kind === 'theorem' && request.keepSlots) return
      const selectedBySlot = new Map(result.arg_slots.map((slot, index) => [slot, selected[index]]))
      if (ruleMode && request.kind === 'theorem') {
        const matchingSlot = result.arg_candidates.findIndex((candidates) => initialRuleStepOrd != null && candidates.includes(initialRuleStepOrd))
        const next = Array.from({ length: result.premise_count }, (_, index) => {
          const assigned = selectedBySlot.get(index)
          if (assigned != null) return assigned
          const candidates = result.arg_candidates[index] ?? []
          if (index === matchingSlot && initialRuleStepOrd != null) return initialRuleStepOrd
          return candidates.length === 1 ? candidates[0] : -1
        })
        setArgStepOrds(next)
        if (selected.length !== result.premise_count && next.every((ord) => ord >= 0)) {
          requestSuggestion({ kind: 'theorem', applied_theorem_id: request.applied_theorem_id, arg_step_ords: next })
        }
      } else {
        setArgStepOrds(
          Array.from({ length: result.premise_count }, (_, index) =>
            selectedBySlot.get(index) ?? result.arg_candidates[index]?.[0] ?? -1,
          ),
        )
      }
    },
    onError: (err, request) => {
      if (latestSuggestion.current === request) {
        setError(() => (err instanceof ApiError ? err.message : t("StepForm_379")))
      }
    },
  })

  function requestSuggestion(request: SuggestionRequest) {
    latestSuggestion.current = request
    suggestMutation.mutate(request)
  }

  useEffect(() => {
    if (latestSuggestion.current?.kind !== kind) latestSuggestion.current = null
    if (kind !== 'axiom') setAxiomId('')
    if (kind !== 'theorem') setAppliedTheoremId('')
    setSuggestion(null)
    setEditedDraft(null)
    setMismatch(null)
  }, [kind])

  useEffect(() => {
    if (latestSuggestion.current?.kind === 'theorem') latestSuggestion.current = null
    setAppliedTheoremId('')
    setSuggestion(null)
    setEditedDraft(null)
    setMismatch(null)
    setArgStepOrds([])
  }, [lemmaGoalFormulaId, candidateArgStepOrds])

  function chooseLemma(theoremId: number, asRule = ruleMode) {
    const theorem = provenTheorems.find((item) => item.id === theoremId)
      ?? applicableTheorems.find((item) => item.theorem.id === theoremId)?.theorem
    if (!asRule && theorem && tooFewPremises(theorem)) return
    setAppliedTheoremId(theoremId)
    setSuggestion(null)
    setEditedDraft(null)
    setMismatch(null)
    requestSuggestion({
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
      setAxiomId('')
      setAppliedTheoremId('')
      setAssumptionConclusionId(null)
      setArgStepOrds([])
      setCandidateArgStepOrds([])
      setEditedDraft(null)
      setMismatch(null)
      setSuggestion(null)
      setError(null)
    },
    onError: (err) => {
      const details = argumentMismatch(err)
      setMismatch(details)
      setError(details ? null : () => (err instanceof ApiError ? err.message : t("StepForm_380")))
    },
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
        return axiomId === '' || !subst ? null : { kind, axiom_id: axiomId, subst }
      case 'theorem':
        return suggestion?.applied_proof_id == null || !subst ? null : {
          kind,
          applied_proof_id: suggestion.applied_proof_id,
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
  const commitEnabled = stepInput != null
    && (kind !== 'theorem' || (argStepOrds.length === suggestion?.premise_count && argStepOrds.every((ord) => ord >= 0)))
    && !addStepMutation.isPending && !suggestMutation.isPending
  const runCommit = useCommand('step.commit', () => {
    if (stepInput && commitEnabled) {
      setMismatch(null)
      setError(null)
      addStepMutation.mutate(stepInput)
    }
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
      <option value="" disabled>{t("StepForm_381")}</option>
      {priorSteps.map((step) => <option key={step.ord} value={step.ord}>#{step.ord}</option>)}
    </select>
  )

  const argumentOptions = suggestion?.arg_candidates.map((candidates) => {
    const exact = new Set(changedSubstitution ? [] : candidates)
    return priorSteps.map((step) => {
      const tokens = proofState?.established.find((item) => item.ord === step.ord)?.tokens
        ?? proofState?.open_assumptions.find((item) => item.step_ord === step.ord)?.tokens
      const tree = tokens && tokensToTree(tokens, symbolsById).tree
      const formula = tree ? renderPreview(tree, symbolsById) : step.conclusion_formula.description
      return { ord: step.ord, matches: exact.has(step.ord), formula: formula?.slice(0, 100) }
    }).sort((left, right) => Number(right.matches) - Number(left.matches))
  }) ?? []

  return (
    <div ref={formRef} data-step-form data-rule-enabled={showRules} className="space-y-4 rounded-lg border border-slate-200 p-4">
      <div>
        <div className="mb-2 text-xs font-medium text-slate-500">{t("StepForm_382")}</div>
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
          {showRules && <button type="button" onClick={() => { setKind('theorem'); setRuleMode(true) }} className={`rounded px-3 py-1.5 text-xs ${kind === 'theorem' && ruleMode ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}>{t("commands_076")}</button>}
        </div>
      </div>

      {kind === 'premise' && (
        <label className="block text-xs text-slate-500">
          {t("StepForm_384")}<select
            value={premiseOrd}
            onChange={(event) => setPremiseOrd(Number(event.target.value))}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>{t("StepForm_381")}</option>
            {premises.map((premise) => (
              <option key={premise.ord} value={premise.ord}>{t("InferenceRulePicker_229")}{premise.ord + 1}{t("StepForm_387")}{premise.formula.id}）</option>
            ))}
          </select>
        </label>
      )}

      {kind === 'axiom' && (
        <label className="block text-xs text-slate-500">
          {t("StepForm_388")}<select
            value={axiomId}
            onChange={(event) => {
              const id = Number(event.target.value)
              setAxiomId(id)
              setSuggestion(null)
              setEditedDraft(null)
              setMismatch(null)
              requestSuggestion({ kind: 'axiom', axiom_id: id })
            }}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>{t("StepForm_381")}</option>
            {axioms.map((axiom) => <option key={axiom.id} value={axiom.id}>{axiom.name}</option>)}
          </select>
        </label>
      )}

      {kind === 'theorem' && (
        <div className="space-y-3">
          {ruleMode && <InferenceRulePicker testId="step-rule-picker" selectedId={appliedTheoremId} onChoose={(theorem) => chooseLemma(theorem.id)} />}
          {!ruleMode && <>
          <div className="rounded border border-indigo-100 bg-indigo-50 p-3">
            <div className="text-xs font-medium text-indigo-900">{t("StepForm_390")}</div>
            <div className="mt-2 text-xs text-slate-600">{t("StepForm_391")}</div>
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
              {priorSteps.length === 0 && <span className="text-xs text-slate-400">{t("StepForm_392")}</span>}
            </div>
            <div className="mt-3 text-xs text-slate-600">{t("StepForm_393")}</div>
            <div className="mt-1 rounded bg-white p-2">
              <FormulaPicker value={lemmaGoalFormulaId} onChange={setLemmaGoalFormulaId} context={context} />
            </div>
          </div>

          {hasLemmaConstraints && (
            <div className="rounded border border-slate-200 p-3">
              <div className="text-xs font-medium text-slate-700">
                {t("StepForm_394")}{applicableFetching ? t("StepForm_395") : t("StepForm_396", applicableTheorems.length)}
              </div>
              <div className="mt-2 space-y-1">
                {concreteApplicable.map((item) => (
                  <button
                    key={item.theorem.id}
                    type="button"
                    disabled={tooFewPremises(item.theorem) || (lemmaGoalFormulaId != null && lemmaGoalFormula == null)}
                    onClick={() => chooseLemma(item.theorem.id)}
                    className="block w-full rounded px-2 py-1 text-left text-sm text-slate-700 hover:bg-indigo-50 disabled:opacity-40"
                  >
                    {item.theorem.name}
                  </button>
                ))}
              </div>
              {schematicApplicable.length > 0 && (
                <details className="mt-2 text-xs text-slate-600">
                  <summary className="cursor-pointer">{t("StepForm_397")}{schematicApplicable.length} {t("StepForm_398")}</summary>
                  <div className="mt-1 space-y-1 pl-2">
                    {schematicApplicable.map((item) => (
                      <button
                        key={item.theorem.id}
                        type="button"
                        disabled={tooFewPremises(item.theorem) || (lemmaGoalFormulaId != null && lemmaGoalFormula == null)}
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
                <p className="mt-2 text-xs text-slate-500">{t("StepForm_399")}</p>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs text-slate-500">
              {t("StepForm_400")}<input
                value={lemmaSearch}
                onChange={(event) => setLemmaSearch(event.target.value)}
                placeholder={t("StepForm_401")}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>
            <select
              aria-label={t("stepChooseLemma")}
              value={appliedTheoremId}
              onChange={(event) => {
                const id = Number(event.target.value)
                chooseLemma(id)
              }}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>{t("StepForm_381")}</option>
              {lemmaOptions.map((item) => (
                <option key={item.id} value={item.id} disabled={tooFewPremises(item)}>
                  {item.name}{tooFewPremises(item) && ` — ${t('stepTooFewPremises')}`}
                </option>
              ))}
            </select>
          </div>
          </>}
          {suggestion && Array.from({ length: suggestion.premise_count }, (_, index) => (
            <div key={index} className="block text-xs text-slate-500">
              <label>
              {t("InferenceRulePicker_229")}{index + 1} {t("StepForm_404")}<select
                value={argStepOrds[index] ?? -1}
                disabled={suggestMutation.isPending}
                onChange={(event) => {
                  const next = [...argStepOrds]
                  next[index] = Number(event.target.value)
                  setArgStepOrds(next)
                  setMismatch(null)
                  setError(null)
                  if (appliedTheoremId !== '' && !editedDraft && next.every((ord) => ord >= 0)
                    && !suggestion.arg_candidates[index]?.includes(next[index])) {
                    requestSuggestion({
                      kind: 'theorem',
                      applied_theorem_id: appliedTheoremId,
                      arg_step_ords: next,
                      keepSlots: true,
                      goal_tokens: ruleMode ? undefined : lemmaGoalFormula?.tokens,
                    })
                  }
                }}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              >
                <option value={-1} disabled>{t("StepForm_381")}</option>
                {(argumentOptions[index] ?? []).map(({ ord, matches, formula }) => (
                  <option key={ord} value={ord}>
                    #{ord}{matches && ` [${t('stepArgumentMatch')}]`}{t("StepForm_406", formula ?? t("StepForm_407"))}
                  </option>
                ))}
              </select>
              </label>
              {ruleMode && (suggestion.arg_candidates[index]?.length ?? 0) > 1 && <p className="mt-1 text-amber-700">{t("StepForm_408")}</p>}
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
          <label className="text-xs text-slate-500">{t("StepForm_409")}{priorOptions(antecedentOrd, setAntecedentOrd)}</label>
          <label className="text-xs text-slate-500">{t("StepForm_410")}{priorOptions(implicationOrd, setImplicationOrd)}</label>
        </div>
      )}

      {kind === 'gen' && (
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">{t("StepForm_411")}{priorOptions(bodyOrd, setBodyOrd)}</label>
          <label className="text-xs text-slate-500">
            {t("StepForm_412")}<select
              value={genVarId}
              onChange={(event) => setGenVarId(Number(event.target.value))}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>{t("StepForm_381")}</option>
              {termVars.map((symbol) => <option key={symbol.id} value={symbol.id}>{symbol.name}</option>)}
            </select>
          </label>
        </div>
      )}

      {kind === 'imp_intro' && (
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-slate-500">
            {t("StepForm_414")}<select
              value={assumptionOrd}
              onChange={(event) => setAssumptionOrd(Number(event.target.value))}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>{t("StepForm_381")}</option>
              {priorSteps.filter((step) => step.step_kind === 'assumption').map((step) => (
                <option key={step.ord} value={step.ord}>#{step.ord}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">{t("StepForm_416")}{priorOptions(bodyOrd, setBodyOrd)}</label>
        </div>
      )}

      {kind === 'assumption' && (
        <div>
          <div className="mb-1 text-xs text-slate-500">{t("StepForm_417")}</div>
          <FormulaPicker value={assumptionConclusionId} onChange={setAssumptionConclusionId} context={context} />
        </div>
      )}

      {suggestedConclusionLatex && (
        <div className="rounded border border-indigo-100 bg-white px-3 py-2">
          <div className="mb-1 text-xs text-slate-500">{t('stepSuggestedConclusion')}</div>
          <Latex display>{suggestedConclusionLatex}</Latex>
        </div>
      )}
      {suggestion && draft && (
        <fieldset disabled={suggestMutation.isPending || addStepMutation.isPending}>
          <SubstitutionEditor
            inference={suggestion}
            draft={draft}
            onChange={(next) => { setEditedDraft(next); setMismatch(null); setError(null) }}
            symbolsById={symbolsById}
            context={context}
          />
        </fieldset>
      )}

      <button
        type="button"
        disabled={!commitEnabled}
        onClick={() => runCommit()}
        className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
      >
        {t("StepForm_422")}<kbd aria-hidden="true" className="ml-1 text-xs">Ctrl/⌘ Enter</kbd>
      </button>
      {mismatch && <ArgumentMismatchMessage details={mismatch} symbolsById={symbolsById} />}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
