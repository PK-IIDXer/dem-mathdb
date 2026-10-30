import { useDisplayError } from "../i18n/useDisplayError"
import { locale } from '../i18n/language'
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { usePageTitle } from '../hooks/usePageTitle'
import { PublicIdRoute } from '../components/PublicIdRoute'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { explorationsApi } from '../api/explorations'
import { proofsApi } from '../api/proofs'
import { symbolsApi } from '../api/symbols'
import { FormulaPicker } from '../components/FormulaPicker'
import { FormulaPreview } from '../components/FormulaPreview'
import { ProofStepList } from '../components/ProofStepList'
import { StepJustification } from '../components/ProofStepJustification'
import { useLemmasByProofId } from '../components/useLemmasByProofId'
import { StepForm } from '../components/StepForm'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'
import type { ExplorationPromotion } from '../api/types'


export function ExplorationsPage() {
  useLanguage()

  const { id } = useParams<{ id: string }>()
  return id == null ? <ExplorationList /> : <PublicIdRoute><ExplorationDetail refId={id} /></PublicIdRoute>
}


function ExplorationList() {
  useLanguage()

  usePageTitle(t("App_030"))
  const readOnly = useReadOnly()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: notes = [] } = useQuery({
    queryKey: ['explorations'],
    queryFn: () => explorationsApi.list(),
  })
  const [name, setName] = useState('')
  const [premiseIds, setPremiseIds] = useState<(number | null)[]>([])
  const [error, setError] = useDisplayError()
  const createMutation = useMutation({
    mutationFn: () => explorationsApi.create({
      name: name.trim(),
      premise_formula_ids: premiseIds.filter((value): value is number => value != null),
    }),
    onSuccess: (note) => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['explorations'] })
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      navigate(`/explorations/${note.theorem.public_id}`)
    },
    onError: (err) => setError(() => (err instanceof ApiError ? err.message : t("ExplorationsPage_613"))),
  })

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold text-slate-900">{t("App_030")}</h2>
        <p className="mt-1 text-sm text-slate-600">
          {t("ExplorationsPage_615")}</p>
      </header>

      {!readOnly && (
        <section className="rounded-lg border border-slate-200 p-4">
          <h3 className="text-sm font-semibold text-slate-700">{t("ExplorationsPage_616")}</h3>
          <label className="mt-3 block text-xs text-slate-500">
            {t("ExplorationsPage_617")}<input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="mt-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">{t("ExplorationsPage_618")}</span>
              <button
                type="button"
                onClick={() => setPremiseIds((current) => [...current, null])}
                className="text-xs font-semibold text-indigo-700 hover:underline"
              >
                {t("ExplorationsPage_619")}</button>
            </div>
            {premiseIds.map((formulaId, index) => (
              <div key={index} className="rounded border border-slate-100 p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
                  <span>{t("InferenceRulePicker_229")}{index + 1}</span>
                  <button
                    type="button"
                    onClick={() => setPremiseIds((current) => current.filter((_, item) => item !== index))}
                    className="text-red-600 hover:underline"
                  >
                    {t("ExplorationsPage_621")}</button>
                </div>
                <FormulaPicker
                  value={formulaId}
                  onChange={(value) => setPremiseIds((current) => current.map((item, itemIndex) => (
                    itemIndex === index ? value : item
                  )))}
                />
              </div>
            ))}
            {premiseIds.length === 0 && (
              <p className="text-xs text-slate-400">{t("ExplorationsPage_622")}</p>
            )}
          </div>
          <button
            type="button"
            disabled={!name.trim() || premiseIds.some((value) => value == null) || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="mt-4 rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {t("ExplorationsPage_623")}</button>
          {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
        </section>
      )}

      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("ExplorationsPage_624")}</h3>
        {notes.length === 0 ? (
          <p className="text-sm text-slate-400">{t("ExplorationsPage_625")}</p>
        ) : (
          <ul className="space-y-2">
            {notes.map((note) => (
              <li key={note.theorem.id}>
                <Link
                  to={`/explorations/${note.theorem.public_id}`}
                  className="block rounded border border-slate-100 px-3 py-2 hover:border-indigo-300 hover:bg-indigo-50/40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-800">{note.theorem.name}</span>
                    <span className="text-xs text-slate-500">{note.step_count} {t("ExplorationsPage_626")}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-600">
                    {note.premises.map((formula, index) => (
                      <span key={formula.id}>{t("InferenceRulePicker_229")}{index + 1}: <FormulaPreview formulaId={formula.id} /></span>
                    ))}
                    {note.premises.length === 0 && <span>{t("ExplorationsPage_628")}</span>}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-400">
                    {t("ExplorationsPage_629")}{new Date(note.updated_at).toLocaleString(locale())}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}


function ExplorationDetail({ refId }: { refId: string }) {
  useLanguage()

  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const [selectedOrd, setSelectedOrd] = useState<number | null>(null)
  const [selectedRuleStepOrd, setSelectedRuleStepOrd] = useState<number | null>(null)
  const [promotionName, setPromotionName] = useState('')
  const [promotion, setPromotion] = useState<ExplorationPromotion | null>(null)
  const [promotionError, setPromotionError] = useDisplayError()
  const { data: note } = useQuery({
    queryKey: ['explorations', refId],
    queryFn: () => explorationsApi.get(refId),
  })
  const proofId = note?.proof.id ?? 0
  const stepsQuery = useQuery({
    queryKey: ['proofs', proofId, 'steps'],
    queryFn: () => proofsApi.listSteps(proofId),
    enabled: note != null,
  })
  const hasStepsData = stepsQuery.data !== undefined
  const steps = stepsQuery.data ?? []
  const lemmasByProofId = useLemmasByProofId(
    proofId,
    note != null && hasStepsData && steps.length > 0,
  )
  useQuery({
    queryKey: ['proofs', proofId, 'formulas'],
    queryFn: async () => {
      const formulas = await proofsApi.listFormulas(proofId)
      for (const formula of formulas) queryClient.setQueryData(['formulas', formula.id], formula)
      return formulas
    },
    enabled: note != null,
    staleTime: Infinity,
  })
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const symbolsById = useMemo(() => new Map(symbols.map((symbol) => [symbol.id, symbol])), [symbols])
  const { data: dependencies } = useQuery({
    queryKey: ['explorations', refId, 'steps', selectedOrd, 'dependencies'],
    queryFn: () => explorationsApi.lineDependencies(refId, Number(selectedOrd)),
    enabled: selectedOrd != null,
  })
  const promoteMutation = useMutation({
    mutationFn: () => explorationsApi.promote(refId, Number(selectedOrd), promotionName.trim()),
    onSuccess: (result) => {
      setPromotion(result)
      setPromotionError(null)
      queryClient.invalidateQueries({ queryKey: ['theorems'] })
      queryClient.invalidateQueries({ queryKey: ['explorations'] })
    },
    onError: (err) => setPromotionError(
      () => (err instanceof ApiError ? err.message : t("ExplorationsPage_630")),
    ),
  })

  function refetchSteps() {
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'steps'] })
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'formulas'] })
    queryClient.invalidateQueries({ queryKey: ['proofs', proofId, 'direct-dependencies'] })
    queryClient.invalidateQueries({ queryKey: ['explorations', refId] })
    queryClient.invalidateQueries({ queryKey: ['explorations'] })
    if (selectedOrd != null) {
      queryClient.invalidateQueries({
        queryKey: ['explorations', refId, 'steps', selectedOrd, 'dependencies'],
      })
    }
  }

  usePageTitle(note?.theorem.name ?? t("App_030"))

  if (!note) return <p className="text-sm text-slate-400">{t("ExplorationsPage_632")}</p>

  return (
    <div className="space-y-6">
      <header>
        <Link to="/explorations" className="text-xs text-indigo-700 hover:underline">{t("ExplorationsPage_633")}</Link>
        <h2 className="mt-2 text-xl font-semibold text-slate-900">{note.theorem.name}</h2>
        <p className="mt-1 text-sm text-slate-600">{t("ExplorationsPage_634")}</p>
      </header>

      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ExplorationsPage_635")}</h3>
        {note.premises.length === 0 ? (
          <p className="text-sm text-slate-400">{t("ExplorationsPage_628")}</p>
        ) : (
          <ol className="space-y-2 text-sm">
            {note.premises.map((formula, index) => (
              <li key={formula.id}>{index + 1}. <FormulaPreview formulaId={formula.id} /></li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ExplorationsPage_637")}{steps.length})</h3>
        <ProofStepList
          proofId={proofId}
          steps={steps}
          highlightOrd={null}
          selectedOrd={selectedOrd}
          onSelect={setSelectedOrd}
          symbolsById={symbolsById}
          renderFormula={(step) => <FormulaPreview formulaId={step.conclusion_formula.id} />}
          renderJustification={(step, symbolMap) => (
            <StepJustification
              step={step}
              symbolsById={symbolMap}
              lemmas={lemmasByProofId}
              onJump={setSelectedOrd}
            />
          )}
          onUseRule={!readOnly ? (ord) => {
            setSelectedRuleStepOrd(ord)
            setSelectedOrd(ord)
          } : undefined}
        />
      </section>

      {selectedOrd != null && (
        <section className="rounded-lg border border-indigo-200 bg-indigo-50 p-4">
          <h3 className="text-sm font-semibold text-indigo-950">{t("ExplorationsPage_638")}{selectedOrd}{t("ExplorationsPage_639")}</h3>
          {!dependencies ? (
            <p className="mt-2 text-sm text-indigo-700">{t("BetaGettingStarted_109")}</p>
          ) : (
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <div>
                <h4 className="text-xs font-semibold text-slate-600">{t("ExplorationsPage_641")}</h4>
                <ul className="mt-1 space-y-1 text-sm">
                  {dependencies.axioms.map((axiom) => (
                    <li key={axiom.id}><Link to={`/axioms/${axiom.public_id}`} className="text-indigo-700 hover:underline">{axiom.name}</Link></li>
                  ))}
                  {dependencies.axioms.length === 0 && <li className="text-slate-400">{t("ExplorationsPage_642")}</li>}
                </ul>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-slate-600">{t("PropositionExplanation_356")}</h4>
                <ul className="mt-1 space-y-1 text-sm">
                  {dependencies.theorems.map((theorem) => (
                    <li key={theorem.id}><Link to={`/theorems/${theorem.public_id}`} className="text-indigo-700 hover:underline">{theorem.name}</Link></li>
                  ))}
                  {dependencies.theorems.length === 0 && <li className="text-slate-400">{t("ExplorationsPage_642")}</li>}
                </ul>
              </div>
            </div>
          )}

          {!readOnly && (
            <div className="mt-4 border-t border-indigo-200 pt-4">
              <label className="block text-xs text-slate-600">
                {t("ExplorationsPage_645")}<input
                  value={promotionName}
                  onChange={(event) => setPromotionName(event.target.value)}
                  className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm"
                />
              </label>
              <button
                type="button"
                disabled={!promotionName.trim() || promoteMutation.isPending}
                onClick={() => promoteMutation.mutate()}
                className="mt-2 rounded bg-indigo-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                {t("ExplorationsPage_646")}</button>
              {promotionError && <p role="alert" className="mt-2 text-sm text-red-700">{promotionError}</p>}
              {promotion && (
                <p className="mt-2 text-sm text-green-700">
                  ✓ <Link to={`/theorems/${promotion.theorem.public_id}`} className="font-semibold underline">{promotion.theorem.name}</Link> {t("ExplorationsPage_647")}</p>
              )}
            </div>
          )}
        </section>
      )}

      {!readOnly && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">{t("ExplorationsPage_648")}</h3>
          <StepForm
            proofId={proofId}
            theoremId={note.theorem.id}
            priorSteps={steps}
            onAdded={refetchSteps}
            initialRuleStepOrd={selectedRuleStepOrd}
          />
        </section>
      )}
    </div>
  )
}
