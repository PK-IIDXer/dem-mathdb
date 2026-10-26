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
  const { id } = useParams<{ id: string }>()
  return id == null ? <ExplorationList /> : <PublicIdRoute><ExplorationDetail refId={id} /></PublicIdRoute>
}


function ExplorationList() {
  usePageTitle('推論ノート')
  const readOnly = useReadOnly()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: notes = [] } = useQuery({
    queryKey: ['explorations'],
    queryFn: () => explorationsApi.list(),
  })
  const [name, setName] = useState('')
  const [premiseIds, setPremiseIds] = useState<(number | null)[]>([])
  const [error, setError] = useState<string | null>(null)
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
    onError: (err) => setError(err instanceof ApiError ? err.message : 'ノートを作成できませんでした'),
  })

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold text-slate-900">推論ノート</h2>
        <p className="mt-1 text-sm text-slate-600">
          結論を先に決めず、命題から推論を重ねて遊ぶ作業場です。
        </p>
      </header>

      {!readOnly && (
        <section className="rounded-lg border border-slate-200 p-4">
          <h3 className="text-sm font-semibold text-slate-700">新しいノート</h3>
          <label className="mt-3 block text-xs text-slate-500">
            名前
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <div className="mt-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-500">出発点の命題（任意）</span>
              <button
                type="button"
                onClick={() => setPremiseIds((current) => [...current, null])}
                className="text-xs font-semibold text-indigo-700 hover:underline"
              >
                前提を追加
              </button>
            </div>
            {premiseIds.map((formulaId, index) => (
              <div key={index} className="rounded border border-slate-100 p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
                  <span>前提 {index + 1}</span>
                  <button
                    type="button"
                    onClick={() => setPremiseIds((current) => current.filter((_, item) => item !== index))}
                    className="text-red-600 hover:underline"
                  >
                    削除
                  </button>
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
              <p className="text-xs text-slate-400">前提なしでも始められます。</p>
            )}
          </div>
          <button
            type="button"
            disabled={!name.trim() || premiseIds.some((value) => value == null) || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="mt-4 rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            ノートを作る
          </button>
          {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
        </section>
      )}

      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">作業中のノート</h3>
        {notes.length === 0 ? (
          <p className="text-sm text-slate-400">まだノートがありません。</p>
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
                    <span className="text-xs text-slate-500">{note.step_count} 行</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-600">
                    {note.premises.map((formula, index) => (
                      <span key={formula.id}>前提 {index + 1}: <FormulaPreview formulaId={formula.id} /></span>
                    ))}
                    {note.premises.length === 0 && <span>前提なし</span>}
                  </div>
                  <div className="mt-1 text-[11px] text-slate-400">
                    更新 {new Date(note.updated_at).toLocaleString()}
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
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const [selectedOrd, setSelectedOrd] = useState<number | null>(null)
  const [selectedRuleStepOrd, setSelectedRuleStepOrd] = useState<number | null>(null)
  const [promotionName, setPromotionName] = useState('')
  const [promotion, setPromotion] = useState<ExplorationPromotion | null>(null)
  const [promotionError, setPromotionError] = useState<string | null>(null)
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
      err instanceof ApiError ? err.message : '定理に昇格できませんでした',
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

  usePageTitle(note?.theorem.name ?? '推論ノート')

  if (!note) return <p className="text-sm text-slate-400">ノートを読み込み中…</p>

  return (
    <div className="space-y-6">
      <header>
        <Link to="/explorations" className="text-xs text-indigo-700 hover:underline">← 推論ノート</Link>
        <h2 className="mt-2 text-xl font-semibold text-slate-900">{note.theorem.name}</h2>
        <p className="mt-1 text-sm text-slate-600">結論を決めず、正しい推論を一行ずつ追加します。</p>
      </header>

      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">出発点の命題</h3>
        {note.premises.length === 0 ? (
          <p className="text-sm text-slate-400">前提なし</p>
        ) : (
          <ol className="space-y-2 text-sm">
            {note.premises.map((formula, index) => (
              <li key={formula.id}>{index + 1}. <FormulaPreview formulaId={formula.id} /></li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">推論の行 ({steps.length})</h3>
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
          <h3 className="text-sm font-semibold text-indigo-950">行 ({selectedOrd}) の依存</h3>
          {!dependencies ? (
            <p className="mt-2 text-sm text-indigo-700">読み込み中…</p>
          ) : (
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <div>
                <h4 className="text-xs font-semibold text-slate-600">使用公理</h4>
                <ul className="mt-1 space-y-1 text-sm">
                  {dependencies.axioms.map((axiom) => (
                    <li key={axiom.id}><Link to={`/axioms/${axiom.public_id}`} className="text-indigo-700 hover:underline">{axiom.name}</Link></li>
                  ))}
                  {dependencies.axioms.length === 0 && <li className="text-slate-400">なし</li>}
                </ul>
              </div>
              <div>
                <h4 className="text-xs font-semibold text-slate-600">引用した定理</h4>
                <ul className="mt-1 space-y-1 text-sm">
                  {dependencies.theorems.map((theorem) => (
                    <li key={theorem.id}><Link to={`/theorems/${theorem.public_id}`} className="text-indigo-700 hover:underline">{theorem.name}</Link></li>
                  ))}
                  {dependencies.theorems.length === 0 && <li className="text-slate-400">なし</li>}
                </ul>
              </div>
            </div>
          )}

          {!readOnly && (
            <div className="mt-4 border-t border-indigo-200 pt-4">
              <label className="block text-xs text-slate-600">
                新しい定理の名前
                <input
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
                定理に昇格
              </button>
              {promotionError && <p role="alert" className="mt-2 text-sm text-red-700">{promotionError}</p>}
              {promotion && (
                <p className="mt-2 text-sm text-green-700">
                  ✓ <Link to={`/theorems/${promotion.theorem.public_id}`} className="font-semibold underline">{promotion.theorem.name}</Link> を検証済みの定理として作成しました。
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {!readOnly && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">推論を一行追加</h3>
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
