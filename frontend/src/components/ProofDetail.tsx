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
import { StepForm } from './StepForm'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'
import type { LemmaDependency, ProofStep, ProofStepFollowup, PropSubst, Symbol, TermSubst, Token } from '../api/types'
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

export function ProofDetail({ proofId, theoremId, context = {}, onboarding = false }: {
  proofId: number
  theoremId: number
  context?: Record<string, number>
  onboarding?: boolean
}) {
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
  const { data: directDependencies } = useQuery({
    queryKey: ['proofs', proofId, 'direct-dependencies'],
    queryFn: () => proofsApi.listDirectDependencies(proofId),
    enabled: hasStepsData && steps.length > 0,
  })
  const lemmasByProofId = useMemo(() => {
    const byTheorem = new Map((directDependencies?.lemmas ?? []).map((lemma) => [lemma.theorem.id, lemma]))
    const byProof = new Map<number, LemmaDependency>()
    for (const [proofId, theoremId] of Object.entries(directDependencies?.applied_proofs ?? {})) {
      const lemma = byTheorem.get(theoremId)
      if (lemma) byProof.set(Number(proofId), lemma)
    }
    for (const lemma of directDependencies?.lemmas ?? []) byProof.set(lemma.proof_id, lemma)
    return byProof
  }, [directDependencies])
  const { data: axiomSystems = [] } = useQuery({
    queryKey: ['axiomSystems'],
    queryFn: () => axiomsApi.listSystems(),
  })
  const [onboardingError, setOnboardingError] = useState<string | null>(null)
  const onboardingPredicate = symbols.find((symbol) => symbol.name === 'φ¹')
  const onboardingVariableId = Object.values(context)[0]
  const onboardingContext = onboardingPredicate == null || onboardingVariableId == null
    ? null
    : { P: onboardingPredicate.id, x: onboardingVariableId }
  const prepareOnboardingMutation = useMutation({
    mutationFn: async () => {
      if (!onboardingContext) throw new Error('P と x の宣言を読み込めませんでした')

      async function addAxiom(name: 'hilbert_k' | 'hilbert_s', goal: string) {
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
          throw new Error(`${name} の代入を自動決定できませんでした`)
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
      await addAxiom('hilbert_k', 'P(x) -> ((P(x) -> P(x)) -> P(x))')
      await addAxiom('hilbert_k', 'P(x) -> (P(x) -> P(x))')
      await addAxiom(
        'hilbert_s',
        '(P(x) -> ((P(x) -> P(x)) -> P(x))) -> ((P(x) -> (P(x) -> P(x))) -> (P(x) -> P(x)))',
      )
    },
    onSuccess: () => {
      setOnboardingError(null)
      refetchSteps()
    },
    onError: (err) => setOnboardingError(
      err instanceof Error ? err.message : '公理を追加できませんでした',
    ),
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

  const [validateError, setValidateError] = useState<string | null>(null)
  const validateMutation = useMutation({
    mutationFn: () => proofsApi.validate(proofId),
    onSuccess: () => {
      setValidateError(null)
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId] })
      queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'state'] })
      queryClient.invalidateQueries({ queryKey: ['theorems'] })
    },
    onError: (err) => {
      setValidateError(err instanceof ApiError ? err.message : 'unknown error')
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
  const [followupError, setFollowupError] = useState<string | null>(null)
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
      setFollowupError(err instanceof ApiError ? err.message : 'unknown error')
    },
  })

  if (!proof) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <section ref={proofRef} className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold text-slate-800">Proof #{proof.id}</h2>
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
          <h3 className="mb-2 text-sm font-semibold text-slate-700">証明の目標</h3>
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
              ? 'この証明は検証に失敗しています。新しい証明を作り直してください。'
              : proofState.reached_goal
              ? '✓ 目標に到達しています。検証できます。'
              : proofState.established.length === 0
                ? 'この式を導く最初のステップを追加してください。'
                : '最後のステップは、まだ目標に到達していません。'}
          </p>
          {proofState.open_assumptions.length > 0 && (
            <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              <p className="font-semibold">未解消の仮定</p>
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
              ? '証明図'
              : viewMode === 'steps'
                ? `ステップ (${steps.length})`
                : stepsQuery.isError ? '証明' : '証明を読み込み中…'}
          </h3>
          <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-xs">
            <button
              type="button"
              disabled={!hasStepsData}
              onClick={() => runTreeView()}
              className={`rounded px-2.5 py-1 disabled:opacity-40 ${viewMode === 'tree' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              証明図 <kbd aria-hidden="true">v t</kbd>
            </button>
            <button
              type="button"
              disabled={!hasStepsData}
              onClick={() => selectViewMode('steps')}
              className={`rounded px-2.5 py-1 disabled:opacity-40 ${viewMode === 'steps' ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}
            >
              ステップ一覧 <kbd aria-hidden="true">v s</kbd>
            </button>
          </div>
        </div>
        {defaultedToSteps && (
          <p className="mb-2 text-xs text-slate-500">
            {steps.length} ステップあるため、描画に時間がかかる証明図ではなくステップ一覧を表示しています。
          </p>
        )}
        {!hasStepsData && stepsQuery.isError ? (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-4 text-sm text-red-700">
            ステップを読み込めませんでした。
          </p>
        ) : !hasStepsData ? (
          <p className="rounded-lg border border-slate-200 px-3 py-4 text-sm text-slate-400">
            ステップを読み込み中…
          </p>
        ) : formulasPending ? (
          // Waiting here keeps the per-formula requests from starting: a
          // FormulaPreview that mounts before the bulk read lands would fetch
          // its own formula. On an error the views render anyway and fall back
          // to that per-formula path.
          <p className="rounded-lg border border-slate-200 px-3 py-4 text-sm text-slate-400">
            論理式を読み込み中…
          </p>
        ) : viewMode === 'tree' ? steps.length > PROOF_TREE_RENDER_STEP_LIMIT ? (
          <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p>
              この証明は {steps.length} ステップあり、証明図の安全な上限 ({PROOF_TREE_RENDER_STEP_LIMIT} ステップ) を超えるため描画しません。
            </p>
            <button
              type="button"
              onClick={() => runStepsView()}
              className="mt-2 font-semibold text-indigo-700 hover:underline"
            >
              ステップ一覧で確認する
            </button>
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
          <button type="button" onClick={() => document.querySelector<HTMLElement>('[data-step-form]')?.scrollIntoView({ block: 'nearest' })} className="mt-2 text-xs text-indigo-700 hover:underline">step ({selectedRuleStepOrd}) から推論定理を選ぶ</button>
        )}
      </div>

      {!readOnly && proof.status === 'draft' && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">ステップを追加</h3>
          <StepForm proofId={proofId} theoremId={theoremId} priorSteps={steps} onAdded={refetchSteps} context={context} initialRuleStepOrd={onboarding ? null : selectedRuleStepOrd} showRules={!onboarding} />
          {immediateFollowups.length > 0 && (
            <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <h4 className="text-sm font-semibold text-emerald-900">続けて適用できる MP</h4>
              <div className="mt-2 space-y-2">
                {immediateFollowups.map((followup, index) => (
                  <div
                    key={`${followup.antecedent_step_ord}-${followup.implication_step_ord}-${index}`}
                    className="flex flex-wrap items-center justify-between gap-2 text-sm"
                  >
                    <span className="text-emerald-950">
                      <StepRef ord={followup.antecedent_step_ord} onJump={jumpTo} /> と{' '}
                      <StepRef ord={followup.implication_step_ord} onJump={jumpTo} /> から{' '}
                      <TokenPreview
                        tokens={followup.conclusion_tokens}
                        symbolsById={symbolsById}
                        context={context}
                      />
                      {followup.reaches_goal && (
                        <span className="ml-2 font-semibold">（目標に到達）</span>
                      )}
                    </span>
                    <button
                      type="button"
                      disabled={followupMutation.isPending}
                      onClick={() => followupMutation.mutate(followup)}
                      className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      この MP を追加
                    </button>
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
          検証する
        </button>
        {validateError && <p className="mt-2 text-sm text-red-700">{validateError}</p>}
        {proof.status === 'verified' && (
          <p className="mt-2 text-sm text-green-700">✓ 検証成功。定理は proven に昇格しました。</p>
        )}
      </div>
      )}

      {proof.status === 'verified' && (
        <div className="rounded-lg border border-slate-200 p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">
            使用している公理 ({usedAxioms.length})
          </h3>
          <ul className="mb-3 space-y-1 text-sm">
            {usedAxioms.map((axiom) => (
              <li key={axiom.id}>
                <Link to={`/axioms/${axiom.public_id}`} className="text-indigo-600 hover:underline">
                  #{axiom.id} {axiom.name}
                </Link>
              </li>
            ))}
          </ul>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">公理系での妥当性</h3>
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
                公理系を選択…
              </option>
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
              判定
            </button>
            {validInSystem != null && (
              <span className={`text-sm font-semibold ${validInSystem ? 'text-green-700' : 'text-red-700'}`}>
                {validInSystem ? '✓ この公理系で成立' : '✗ この公理系では成立しない'}
              </span>
            )}
          </div>
        </div>
      )}

      {onboarding && proof.status === 'draft' && steps.length === 0 && (
        <OnboardingCoach step={3} title="証明する">
          <p>ProofState の「証明の目標」が、あと示す式です。</p>
          <p>まず K と S を検索し、この式に必要な3つの公理インスタンスを実際の proof へ追加します。</p>
          <button
            type="button"
            disabled={onboardingContext == null || prepareOnboardingMutation.isPending}
            onClick={() => prepareOnboardingMutation.mutate()}
            className="w-full rounded bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            公理 K / S を検索して追加
          </button>
          {onboardingError && <p className="text-red-700">{onboardingError}</p>}
        </OnboardingCoach>
      )}
      {onboarding && proof.status === 'draft' && steps.length >= 3 && (
        <OnboardingCoach step={3} title="証明する">
          <p>緑色の［この MP を追加］を押してください。1回目の結論から次の MP が提案されます。</p>
          <p>2回目を押すと、宣言した x への一般化と機械検証が続き、verified になります。</p>
        </OnboardingCoach>
      )}
      {onboarding && proof.status === 'verified' && (
        <OnboardingCoach step={3} title="検証されました">
          <p className="font-semibold text-green-700">✓ 最初の verified theorem に到達しました。</p>
          <p>画面内の証明図と「使用している公理」が、保存・検証された実物です。</p>
          <div className="flex gap-2">
            <Link to="/theorems" className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white">
              自分の定理を書く
            </Link>
            <Link to="/" className="rounded bg-slate-100 px-3 py-1.5 text-xs text-slate-700">
              体系を見る
            </Link>
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

function StepRef({ ord, onJump }: { ord: number; onJump: (ord: number) => void }) {
  return (
    <button type="button" onClick={() => onJump(ord)} className="text-indigo-600 hover:underline">
      ({ord})
    </button>
  )
}

function StepRefList({ ords, onJump }: { ords: number[]; onJump: (ord: number) => void }) {
  return (
    <>
      {ords.map((ord, i) => (
        <span key={ord}>
          {i > 0 && ', '}
          <StepRef ord={ord} onJump={onJump} />
        </span>
      ))}
    </>
  )
}

function SubstSummary({
  termSubsts,
  propSubsts,
  symbolsById,
}: {
  termSubsts: TermSubst[]
  propSubsts: PropSubst[]
  symbolsById: Map<number, Symbol>
}) {
  const [open, setOpen] = useState(false)
  if (termSubsts.length === 0 && propSubsts.length === 0) return null
  return (
    <span className="ml-1">
      <button type="button" onClick={() => setOpen((v) => !v)} className="text-slate-400 hover:text-slate-600">
        [代入 {open ? '▲' : '▼'}]
      </button>
      {open && (
        <span className="ml-1 inline-flex flex-wrap items-center gap-x-2">
          {termSubsts.map((subst, i) => (
            <span key={`t${i}`} className="whitespace-nowrap">
              {symbolsById.get(subst.source_symbol_id)?.name ?? `#${subst.source_symbol_id}`} ↦{' '}
              <FormulaPreview formulaId={subst.target_formula_id} />
            </span>
          ))}
          {propSubsts.map((subst, i) => (
            <span key={`p${i}`} className="whitespace-nowrap">
              {symbolsById.get(subst.source_symbol_id)?.name ?? `#${subst.source_symbol_id}`} ↦{' '}
              <FormulaPreview formulaId={subst.body_formula_id} />
            </span>
          ))}
        </span>
      )}
    </span>
  )
}

function StepJustification({
  step,
  symbolsById,
  lemmas,
  onJump,
}: {
  step: ProofStep
  symbolsById: Map<number, Symbol>
  lemmas: Map<number, LemmaDependency>
  onJump: (ord: number) => void
}) {
  switch (step.step_kind) {
    case 'premise':
      return <span>前提 #{step.premise_ord}</span>
    case 'assumption':
      return <span>仮定（⇒導入で落とす）</span>
    case 'axiom':
      return (
        <span>
          公理{' '}
          {step.axiom ? (
            <Link to={`/axioms/${step.axiom.public_id}`} className="text-indigo-600 hover:underline">
              {step.axiom.name}
            </Link>
          ) : (
            '?'
          )}
          <SubstSummary termSubsts={step.term_substs} propSubsts={step.prop_substs} symbolsById={symbolsById} />
        </span>
      )
    case 'theorem':
      return (
        <span>
          既証明の適用{' '}
          {step.applied_proof_id != null && (
            <Link to={`/proofs/${step.applied_proof_id}`} className="text-indigo-600 hover:underline">
              {lemmas.get(step.applied_proof_id)?.theorem.name ?? `Proof #${step.applied_proof_id}`}
            </Link>
          )}
          {step.arg_step_ords.length > 0 && (
            <>
              {' '}
              (<StepRefList ords={step.arg_step_ords} onJump={onJump} />)
            </>
          )}
          <SubstSummary termSubsts={step.term_substs} propSubsts={step.prop_substs} symbolsById={symbolsById} />
        </span>
      )
    case 'rule':
      if (step.inference_rule?.kind === 'modus_ponens') {
        return (
          <span>
            MP <StepRefList ords={step.arg_step_ords} onJump={onJump} />
          </span>
        )
      }
      if (step.inference_rule?.kind === 'generalization') {
        return (
          <span>
            Gen <StepRefList ords={step.arg_step_ords} onJump={onJump} />
            {step.gen_variable_symbol_id != null && (
              <> (var: {symbolsById.get(step.gen_variable_symbol_id)?.name ?? `#${step.gen_variable_symbol_id}`})</>
            )}
          </span>
        )
      }
      if (step.inference_rule?.kind === 'implication_intro') {
        const [assumptionOrd, bodyOrd] = step.arg_step_ords
        return (
          <span>
            ⇒導入 (仮定 <StepRefList ords={assumptionOrd != null ? [assumptionOrd] : []} onJump={onJump} /> を{' '}
            <StepRefList ords={bodyOrd != null ? [bodyOrd] : []} onJump={onJump} /> から落とす)
          </span>
        )
      }
      return <span>{step.inference_rule?.kind ?? 'rule'}</span>
    default:
      return null
  }
}
