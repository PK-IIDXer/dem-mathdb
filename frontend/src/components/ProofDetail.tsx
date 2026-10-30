import { useDisplayError } from "../i18n/useDisplayError"
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { ONBOARDING_AXIOMS, findOnboardingPredicate } from '../onboarding'
import { SystemValidityNote } from './BetaIdentity'
import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import { axiomsApi } from '../api/axioms'
import { symbolsApi } from '../api/symbols'
import { formulasApi } from '../api/formulas'
import { FormulaPreview } from './FormulaPreview'
import { Latex } from './Latex'
import { renderLatex, renderPreview, tokensToTree } from './FormulaEditor/model'
import { symbolsWithDeclarationNames } from './FormulaEditor/display'
import { ProofTree } from './ProofTree'
import { PropositionExplanation } from './PropositionExplanation'
import { ProofStepList, type ProofStepListHandle } from './ProofStepList'
import { StepJustification, StepRef } from './ProofStepJustification'
import { useLemmasByProofId } from './useLemmasByProofId'
import { StepForm } from './StepForm'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'
import type { ProofStepFollowup, Symbol, Token } from '../api/types'
import { OnboardingCoach } from './OnboardingCoach'
import { TopDownProofEditor } from './TopDownProofEditor'
import { useCommand } from '../commands/CommandProvider'

const STATUS_COLOR: Record<string, string> = {
  draft: 'bg-slate-200 text-slate-700',
  verified: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
}

export const PROOF_TREE_DEFAULT_STEP_LIMIT = 100
export const PROOF_TREE_RENDER_STEP_LIMIT = 250

export function ProofDetail({ proofId, theoremId, theoremName = t("ProofDetail_234"), proofNumber, context = {}, onboarding = false }: {
  proofId: number
  theoremId: number
  theoremName?: string
  proofNumber?: number
  context?: Record<string, number>
  onboarding?: boolean
}) {
  useLanguage()

  const readOnly = useReadOnly()
  const proofRef = useRef<HTMLElement>(null)
  const queryClient = useQueryClient()
  const { data: proof } = useQuery({ queryKey: ['proofs', proofId], queryFn: () => proofsApi.get(proofId) })
  const stepsQuery = useQuery({
    queryKey: ['proofs', proofId, 'steps'],
    queryFn: () => proofsApi.listSteps(proofId),
  })
  const hasStepsData = stepsQuery.data !== undefined
  const steps = stepsQuery.data ?? []
  const { data: proofState } = useQuery({
    queryKey: ['proofs', proofId, 'state'],
    queryFn: () => proofsApi.getState(proofId),
  })
  // One request for every formula the step list and the proof figure will show.
  // Priming happens inside the queryFn, so the cache is already filled by the
  // time this query resolves and the views below mount: each FormulaPreview
  // then reads its formula straight from the cache instead of fetching it.
  const { isPending: formulasPending } = useQuery({
    queryKey: ['proofs', proofId, 'formulas'],
    queryFn: async () => {
      const formulas = await proofsApi.listFormulas(proofId)
      for (const formula of formulas) {
        queryClient.setQueryData(['formulas', formula.id], formula)
      }
      return formulas
    },
    staleTime: Infinity,
  })
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols() })
  const symbolsById = useMemo(() => new Map(symbols.map((s) => [s.id, s])), [symbols])
  const lemmasByProofId = useLemmasByProofId(proofId, hasStepsData && steps.length > 0)
  const { data: axiomSystems = [] } = useQuery({
    queryKey: ['axiomSystems'],
    queryFn: () => axiomsApi.listSystems(),
  })
  const [onboardingError, setOnboardingError] = useDisplayError()
  const onboardingPredicate = findOnboardingPredicate(symbols)
  const onboardingVariableId = Object.values(context)[0]
  const onboardingContext = onboardingPredicate == null || onboardingVariableId == null
    ? null
    : { P: onboardingPredicate.id, x: onboardingVariableId }
  const prepareOnboardingMutation = useMutation({
    mutationFn: async () => {
      if (!onboardingContext) throw new Error(t("ProofDetail_235"))

      async function addAxiom(name: typeof ONBOARDING_AXIOMS[number], goal: string) {
        const [axiom, parsed] = await Promise.all([
          axiomsApi.getByName(name),
          formulasApi.parse(goal, onboardingContext as Record<string, number>),
        ])
        const suggestion = await proofsApi.suggestStep(proofId, {
          kind: 'axiom',
          axiom_id: axiom.id,
          goal_tokens: parsed.tokens,
        })
        if (suggestion.undetermined.length > 0) {
          throw new Error(t("ProofDetail_236", name))
        }
        await proofsApi.addStep(proofId, {
          kind: 'axiom',
          axiom_id: axiom.id,
          subst: suggestion.subst,
        })
      }

      // Put both K antecedents before S. Once S is appended, the ordinary
      // follow-up endpoint can offer MP; its conclusion is itself an
      // implication, so the same endpoint offers the second MP.
      if (steps.length === 0) await addAxiom(ONBOARDING_AXIOMS[0], 'P(x) -> ((P(x) -> P(x)) -> P(x))')
      if (steps.length <= 1) await addAxiom(ONBOARDING_AXIOMS[0], 'P(x) -> (P(x) -> P(x))')
      if (steps.length <= 2) await addAxiom(
        ONBOARDING_AXIOMS[1],
        '(P(x) -> ((P(x) -> P(x)) -> P(x))) -> ((P(x) -> (P(x) -> P(x))) -> (P(x) -> P(x)))',
      )
    },
    onSuccess: () => {
      setOnboardingError(null)
      refetchSteps()
    },
    onError: (err) => {
      setOnboardingError(() => (err instanceof Error ? err.message : t("ProofDetail_237")))
      refetchSteps()
    },
  })

  const [highlightOrd, setHighlightOrd] = useState<number | null>(null)
  const [selectedRuleStepOrd, setSelectedRuleStepOrd] = useState<number | null>(null)
  const stepListRef = useRef<ProofStepListHandle>(null)
  const [viewSelection, setViewSelection] = useState<{
    proofId: number
    mode: 'tree' | 'steps'
  } | null>(null)
  const selectedViewMode = viewSelection?.proofId === proofId ? viewSelection.mode : null
  const defaultViewMode = hasStepsData
    ? steps.length >= PROOF_TREE_DEFAULT_STEP_LIMIT ? 'steps' : 'tree'
    : null
  const viewMode = selectedViewMode ?? defaultViewMode
  const defaultedToSteps = selectedViewMode == null && defaultViewMode === 'steps'

  function selectViewMode(mode: 'tree' | 'steps') {
    setViewSelection({ proofId, mode })
  }

  function jumpTo(ord: number) {
    setSelectedRuleStepOrd(ord)
    selectViewMode('steps')
    window.setTimeout(() => {
      stepListRef.current?.scrollToOrd(ord)
      setHighlightOrd(ord)
      window.setTimeout(() => setHighlightOrd((current) => (current === ord ? null : current)), 1500)
    }, 0)
  }

  const [validateError, setValidateError] = useDisplayError()
  const validateMutation = useMutation({
    mutationFn: () => proofsApi.validate(proofId),
    onSuccess: () => {
      setValidateError(null)
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId] })
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'state'] })
      queryClient.invalidateQueries({ queryKey: ['theorems'] })
    },
    onError: (err) => {
      setValidateError(() => (err instanceof ApiError ? err.message : 'unknown error'))
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId] })
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'state'] })
    },
  })
  const runTreeView = useCommand('proof.view.tree', () => selectViewMode('tree'), {
    enabled: hasStepsData,
    scope: proofRef,
  })
  const runStepsView = useCommand('proof.view.steps', () => selectViewMode('steps'), {
    enabled: hasStepsData,
    scope: proofRef,
  })
  const runValidate = useCommand('proof.validate', () => validateMutation.mutate(), {
    enabled: proof?.status === 'draft' && !validateMutation.isPending,
    scope: proofRef,
  })

  const { data: usedAxioms = [] } = useQuery({
    queryKey: ['proofs', proofId, 'used-axioms'],
    queryFn: () => proofsApi.listUsedAxioms(proofId),
    enabled: proof?.status === 'verified',
  })

  const [systemId, setSystemId] = useState<number | ''>('')
  const [validInSystem, setValidInSystem] = useState<boolean | null>(null)
  const checkSystemMutation = useMutation({
    mutationFn: () => proofsApi.isValidInSystem(proofId, Number(systemId)),
    onSuccess: (result) => setValidInSystem(result.is_subset),
  })

  function refetchSteps() {
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'steps'] })
    // a new step brings a new conclusion formula into the proof
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'formulas'] })
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'state'] })
    // a new theorem step can cite a theorem whose name is not loaded yet
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'direct-dependencies'] })
  }

  const latestStepOrd = steps.length > 0 ? steps[steps.length - 1].ord : null
  const { data: followups = [] } = useQuery({
    queryKey: ['proofs', proofId, 'steps', latestStepOrd, 'followups'],
    queryFn: () => proofsApi.listStepFollowups(proofId, Number(latestStepOrd)),
    enabled: proof?.status === 'draft' && latestStepOrd != null,
  })
  const immediateFollowups = followups.filter(
    (followup) => followup.implication_step_ord === latestStepOrd,
  )
  const [followupError, setFollowupError] = useDisplayError()
  const followupMutation = useMutation({
    mutationFn: async (followup: ProofStepFollowup) => {
      const mpStep = await proofsApi.addStep(proofId, {
        kind: 'mp',
        antecedent_step_ord: followup.antecedent_step_ord,
        implication_step_ord: followup.implication_step_ord,
      })
      if (onboarding && steps.length === 4 && onboardingVariableId != null) {
        await proofsApi.addStep(proofId, {
          kind: 'gen',
          body_step_ord: mpStep.ord,
          gen_variable_symbol_id: onboardingVariableId,
        })
        await proofsApi.validate(proofId)
      }
      return mpStep
    },
    onSuccess: () => {
      setFollowupError(null)
      refetchSteps()
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId] })
      queryClient.invalidateQueries({ queryKey: ['theorems'] })
    },
    onError: (err) => {
      setFollowupError(() => (err instanceof ApiError ? err.message : 'unknown error'))
      refetchSteps()
    },
  })

  const resumeOnboardingMutation = useMutation({
    mutationFn: async () => {
      if (steps.length === 5 && onboardingVariableId != null) {
        await proofsApi.addStep(proofId, { kind: 'gen', body_step_ord: 4, gen_variable_symbol_id: onboardingVariableId })
      }
      await proofsApi.validate(proofId)
    },
    onSuccess: () => { setFollowupError(null); refetchSteps(); queryClient.invalidateQueries({ queryKey: ['proofs', proofId] }); queryClient.invalidateQueries({ queryKey: ['theorems'] }) },
    onError: (err) => { setFollowupError(() => (err instanceof ApiError ? err.message : 'unknown error')); refetchSteps() },
  })

  if (!proof) return <p className="text-sm text-slate-400">{t("BetaGettingStarted_109")}</p>

  return (
    <section ref={proofRef} className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-800">{theoremName}{t("BetaGettingStarted_105")}{proofNumber != null ? ` (${proofNumber})` : ''}</h2>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_COLOR[proof.status]}`}>
          {proof.status}
        </span>
      </div>

      {proofState && (
        <div
          className={`rounded-lg border p-4 ${
            proof.status === 'rejected'
              ? 'border-red-200 bg-red-50'
              : proofState.reached_goal
              ? 'border-green-200 bg-green-50'
              : 'border-indigo-200 bg-indigo-50'
          }`}
        >
          <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ProofDetail_240")}</h3>
          <div className="text-base text-slate-900">
            <TokenPreview tokens={proofState.goal_tokens} symbolsById={symbolsById} context={context} />
          </div>
          <p
            className={`mt-2 text-sm ${
              proof.status === 'rejected'
                ? 'text-red-800'
                : proofState.reached_goal
                  ? 'text-green-700'
                  : 'text-indigo-800'
            }`}
          >
            {proof.status === 'rejected'
              ? t("ProofDetail_241")
              : proofState.reached_goal
              ? t("ProofDetail_242")
              : proofState.established.length === 0
                ? t("ProofDetail_243")
                : t("ProofDetail_244")}
          </p>
          {proofState.open_assumptions.length > 0 && (
            <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <p className="font-semibold">{t("ProofDetail_245")}</p>
              <ul className="mt-1 space-y-1">
                {proofState.open_assumptions.map((assumption) => (
                  <li key={assumption.step_ord}>
                    <StepRef ord={assumption.step_ord} onJump={jumpTo} />:{' '}
                    <TokenPreview tokens={assumption.tokens} symbolsById={symbolsById} context={context} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!readOnly && proof.status === 'draft' && proofState && (
        <TopDownProofEditor
          key={proofId}
          proofId={proofId}
          proofState={proofState}
          symbols={symbols}
          context={context}
          onAdded={refetchSteps}
          showRules={!onboarding}
        />
      )}

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-700">
            {viewMode === 'tree'
              ? t("ProofDetail_246")
              : viewMode === 'steps'
                ? t("ProofDetail_247", steps.length)
                : stepsQuery.isError ? t("ProofDetail_248") : t("ProofDetail_249")}
          </h3>
          <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-xs">
            <button
              type="button"
              disabled={!hasStepsData}
              onClick={() => runTreeView()}
              className={`rounded px-2.5 py-1 disabled:opacity-40 ${viewMode === 'tree' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              {t("ProofDetail_250")}<kbd aria-hidden="true">v t</kbd>
            </button>
            <button
              type="button"
              disabled={!hasStepsData}
              onClick={() => selectViewMode('steps')}
              className={`rounded px-2.5 py-1 disabled:opacity-40 ${viewMode === 'steps' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              {t("ProofDetail_251")}<kbd aria-hidden="true">v s</kbd>
            </button>
          </div>
        </div>
        {defaultedToSteps && (
          <p className="mb-2 text-xs text-slate-500">
            {steps.length} {t("ProofDetail_252")}</p>
        )}
        {!hasStepsData && stepsQuery.isError ? (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-4 text-sm text-red-700">
            {t("ProofDetail_253")}</p>
        ) : !hasStepsData ? (
          <p className="rounded-lg border border-slate-200 px-3 py-4 text-sm text-slate-400">
            {t("ProofDetail_254")}</p>
        ) : formulasPending ? (
          // Waiting here keeps the per-formula requests from starting: a
          // FormulaPreview that mounts before the bulk read lands would fetch
          // its own formula. On an error the views render anyway and fall back
          // to that per-formula path.
          <p className="rounded-lg border border-slate-200 px-3 py-4 text-sm text-slate-400">
            {t("ProofDetail_255")}</p>
        ) : viewMode === 'tree' ? steps.length > PROOF_TREE_RENDER_STEP_LIMIT ? (
          <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p>
              {t("ProofDetail_256")}{steps.length} {t("ProofDetail_257")}{PROOF_TREE_RENDER_STEP_LIMIT} {t("ProofDetail_258")}</p>
            <button
              type="button"
              onClick={() => runStepsView()}
              className="mt-2 font-semibold text-indigo-700 hover:underline"
            >
              {t("ProofDetail_259")}</button>
          </div>
        ) : (
          <ProofTree proofId={proofId} steps={steps} onSelectStep={jumpTo} symbolsById={symbolsById} lemmas={lemmasByProofId} />
        ) : (
          <ProofStepList
            ref={stepListRef}
            proofId={proofId}
            steps={steps}
            highlightOrd={highlightOrd}
            symbolsById={symbolsById}
            renderFormula={(step) => <PropositionExplanation step={step} symbolsById={symbolsById} lemmas={lemmasByProofId}
              trigger={<FormulaPreview formulaId={step.conclusion_formula.id} />} />}
            renderJustification={(step, symbolMap) => (
              <StepJustification step={step} symbolsById={symbolMap} lemmas={lemmasByProofId} onJump={jumpTo} />
            )}
            onUseRule={!readOnly && proof.status === 'draft' && !onboarding ? setSelectedRuleStepOrd : undefined}
          />
        )}
        {selectedRuleStepOrd != null && !readOnly && proof.status === 'draft' && !onboarding && (
          <button type="button" onClick={() => document.querySelector<HTMLElement>('[data-step-form]')?.scrollIntoView({ block: 'nearest' })} className="mt-2 text-xs text-indigo-700 hover:underline">step ({selectedRuleStepOrd}{t("ProofDetail_260")}</button>
        )}
      </div>

      {!readOnly && proof.status === 'draft' && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ProofDetail_261")}</h3>
          <StepForm proofId={proofId} theoremId={theoremId} priorSteps={steps} onAdded={refetchSteps} context={context} initialRuleStepOrd={onboarding ? null : selectedRuleStepOrd} showRules={!onboarding} />
          {immediateFollowups.length > 0 && (
            <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <h4 className="text-sm font-semibold text-emerald-900">{t("ProofDetail_262")}</h4>
              <div className="mt-2 space-y-2">
                {immediateFollowups.map((followup, index) => (
                  <div
                    key={`${followup.antecedent_step_ord}-${followup.implication_step_ord}-${index}`}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <span className="text-emerald-950">
                      <StepRef ord={followup.antecedent_step_ord} onJump={jumpTo} /> {t("ProofDetail_263")}{' '}
                      <StepRef ord={followup.implication_step_ord} onJump={jumpTo} /> {t("ProofDetail_264")}{' '}
                      <TokenPreview
                        tokens={followup.conclusion_tokens}
                        symbolsById={symbolsById}
                        context={context}
                      />
                      {followup.reaches_goal && (
                        <span className="ml-2 font-semibold">{t("ProofDetail_265")}</span>
                      )}
                    </span>
                    <button
                      type="button"
                      disabled={followupMutation.isPending}
                      onClick={() => followupMutation.mutate(followup)}
                      className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      {t("ProofDetail_266")}</button>
                  </div>
                ))}
              </div>
              {followupError && <p className="mt-2 text-sm text-red-700">{followupError}</p>}
            </div>
          )}
        </div>
      )}

      {!readOnly && (
      <div className="rounded-lg border border-slate-200 p-4">
        <button
          type="button"
          disabled={proof.status === 'verified' || validateMutation.isPending}
          onClick={() => runValidate()}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          {t("ProofDetail_267")}</button>
        {validateError && <p className="mt-2 text-sm text-red-700">{validateError}</p>}
        {proof.status === 'verified' && (
          <p className="mt-2 text-sm text-green-700">{t("ProofDetail_268")}</p>
        )}
      </div>
      )}

      {proof.status === 'verified' && (
        <div className="rounded-lg border border-slate-200 p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">
            {t("ProofDetail_269")}{usedAxioms.length})
          </h3>
          <ul className="mb-3 space-y-1 text-sm">
            {usedAxioms.map((axiom) => (
              <li key={axiom.id}>
                <Link to={`/axioms/${axiom.public_id}`} className="text-indigo-600 hover:underline">
                  {axiom.name}
                </Link>
              </li>
            ))}
          </ul>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ProofDetail_270")}</h3>
          <div className="flex items-center gap-2">
            <select
              value={systemId}
              onChange={(e) => {
                setSystemId(Number(e.target.value))
                setValidInSystem(null)
              }}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>
                {t("ProofDetail_271")}</option>
              {axiomSystems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={systemId === '' || checkSystemMutation.isPending}
              onClick={() => checkSystemMutation.mutate()}
              className="rounded bg-slate-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              {t("ProofDetail_272")}</button>
            <SystemValidityNote namespace={axiomSystems.find(system => system.id === Number(systemId))?.namespace_name} />
          {validInSystem != null && (
              <span className={`text-sm font-semibold ${validInSystem ? 'text-green-700' : 'text-red-700'}`}>
                {validInSystem ? t("ProofDetail_273") : t("ProofDetail_274")}
              </span>
            )}
          </div>
        </div>
      )}

      {onboarding && proof.status === 'draft' && steps.length < 3 && (
        <OnboardingCoach step={3} title={t("ProofDetail_275")}>
          <p>{t("ProofDetail_276")}</p>
          <p>{t("ProofDetail_277")}</p>
          <button
            type="button"
            disabled={onboardingContext == null || prepareOnboardingMutation.isPending || stepsQuery.isFetching}
            onClick={() => prepareOnboardingMutation.mutate()}
            className="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {t("ProofDetail_278")}</button>
          {onboardingError && <p className="text-red-700">{onboardingError}</p>}
        </OnboardingCoach>
      )}
      {onboarding && proof.status === 'draft' && steps.length >= 3 && (
        <OnboardingCoach step={3} title={t("ProofDetail_275")}>
          <p>{t("ProofDetail_280")}</p>
          <p>{t("ProofDetail_281")}</p>
          {steps.length >= 5 && <button type="button" disabled={resumeOnboardingMutation.isPending || stepsQuery.isFetching} onClick={() => resumeOnboardingMutation.mutate()} className="mt-2 rounded bg-indigo-600 px-3 py-2 text-white">{t("ProofDetail_282")}</button>}
        </OnboardingCoach>
      )}
      {onboarding && proof.status === 'verified' && (
        <OnboardingCoach step={3} title={t("ProofDetail_283")}>
          <p className="font-semibold text-green-700">{t("ProofDetail_284")}</p>
          <p>{t("ProofDetail_285")}</p>
          <div className="flex gap-2">
            <Link to="/theorems" className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">
              {t("ProofDetail_286")}</Link>
            <Link to="/" className="rounded bg-slate-100 px-3 py-1.5 text-xs text-slate-700">
              {t("ProofDetail_287")}</Link>
          </div>
        </OnboardingCoach>
      )}
    </section>
  )
}

function TokenPreview({
  tokens,
  symbolsById,
  context,
}: {
  tokens: Token[]
  symbolsById: Map<number, Symbol>
  context: Record<string, number>
}) {
  useLanguage()

  const tree = useMemo(() => tokensToTree(tokens, symbolsById).tree, [tokens, symbolsById])
  const displaySymbolsById = useMemo(
    () => symbolsWithDeclarationNames(symbolsById, context),
    [context, symbolsById],
  )
  const latex = useMemo(
    () => (tree ? renderLatex(tree, displaySymbolsById) : ''),
    [displaySymbolsById, tree],
  )
  const preview = useMemo(
    () => (tree ? renderPreview(tree, displaySymbolsById) : ''),
    [displaySymbolsById, tree],
  )
  return (
    <span>
      <Latex>{latex}</Latex>
      <span className="ml-2 text-xs text-slate-500">{preview}</span>
    </span>
  )
}
