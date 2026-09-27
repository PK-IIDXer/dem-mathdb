import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { formulasApi } from '../api/formulas'
import { symbolsApi } from '../api/symbols'
import { FormulaEditor } from '../components/FormulaEditor'
import { renderLatex, renderPreview, tokensToTree } from '../components/FormulaEditor/model'
import { Latex } from '../components/Latex'
import { useReadOnly } from '../ReadOnlyContext'
import { OnboardingCoach } from '../components/OnboardingCoach'
import { ONBOARDING_FORMULA, onboardingQuery } from '../onboarding'

export function FormulasPage() {
  const readOnly = useReadOnly()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const onboarding = searchParams.get('onboarding') === '1'
  const { data: formulas = [] } = useQuery({
    queryKey: ['formulas'],
    queryFn: () => formulasApi.list(),
  })
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const value = Number(searchParams.get('formula'))
    return Number.isInteger(value) && value > 0 ? value : null
  })
  const { data: onboardingSymbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
    enabled: onboarding,
  })
  const onboardingPredicate = onboardingSymbols.find((symbol) => symbol.name === 'φ¹')

  return (
    <div className="space-y-6">
      {!readOnly && (
      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">論理式を登録</h2>
        <div className={onboarding ? 'rounded-xl ring-4 ring-indigo-200' : ''}>
          <FormulaEditor
            context={onboardingPredicate ? { P: onboardingPredicate.id } : undefined}
            showSuggestions={!onboarding}
            showAdvanced={!onboarding}
            showRemarks={!onboarding}
            onRegistered={(formula) => {
              setSelectedId(formula.id)
              if (onboarding) navigate(`/theorems${onboardingQuery({ formula: formula.id })}`)
            }}
          />
        </div>
      </section>
      )}

      <section className="grid grid-cols-2 gap-4">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">
            登録済みの論理式 ({formulas.length})
          </h2>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-1 pr-3">id</th>
                <th className="py-1 pr-3">type</th>
                <th className="py-1 pr-3">tokens</th>
                <th className="py-1 pr-3">remarks</th>
              </tr>
            </thead>
            <tbody>
              {formulas.map((formula) => (
                <tr
                  key={formula.id}
                  className={`border-t border-slate-100 hover:bg-slate-50 ${
                    selectedId === formula.id ? 'bg-indigo-50' : ''
                  }`}
                >
                  <td className="py-1 pr-3">
                    <button
                      type="button"
                      onClick={() => setSelectedId(formula.id)}
                      aria-pressed={selectedId === formula.id}
                      className="rounded font-medium text-indigo-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                    >
                      {formula.id}
                      <span className="sr-only"> の詳細を表示</span>
                    </button>
                  </td>
                  <td className="py-1 pr-3">{formula.formula_type.name}</td>
                  <td className="py-1 pr-3">{formula.token_count}</td>
                  <td className="py-1 pr-3 text-slate-500">{formula.remarks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">詳細</h2>
          {selectedId != null ? (
            <FormulaDetailView id={selectedId} />
          ) : (
            <p className="text-sm text-slate-400">一覧から論理式を選んでください</p>
          )}
        </div>
      </section>

      {onboarding && (
        <OnboardingCoach step={1} title="式を書いてみる">
          <p>下の欄へ次の式をそのまま入力してください。</p>
          <code className="block rounded bg-slate-100 px-2 py-1">{ONBOARDING_FORMULA}</code>
          <p>数式表示で「任意の x について P(x) なら P(x)」という解釈を確認し、［確認して登録する］を押します。</p>
        </OnboardingCoach>
      )}
    </div>
  )
}

function FormulaDetailView({ id }: { id: number }) {
  const { data: formula } = useQuery({
    queryKey: ['formulas', id],
    queryFn: () => formulasApi.get(id),
  })
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const symbolsById = useMemo(() => new Map(symbols.map((s) => [s.id, s])), [symbols])

  const tree = useMemo(() => {
    if (!formula) return null
    return tokensToTree(formula.tokens, symbolsById).tree
  }, [formula, symbolsById])
  const latex = useMemo(() => (tree ? renderLatex(tree, symbolsById) : ''), [tree, symbolsById])
  const preview = useMemo(() => (tree ? renderPreview(tree, symbolsById) : ''), [tree, symbolsById])

  if (!formula) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-4 text-sm">
      <div className="overflow-x-auto rounded border border-slate-100 bg-white px-3 py-3">
        <Latex display>{latex}</Latex>
      </div>
      <div>
        <span className="text-xs text-slate-500">polish notation: </span>
        <code>{preview}</code>
      </div>
      <div>
        <span className="text-xs text-slate-500">hash: </span>
        <code className="text-xs">{formula.hash}</code>
      </div>
      <div className="text-xs text-slate-500">token_count: {formula.token_count}</div>
      {formula.remarks && <div className="text-slate-600">{formula.remarks}</div>}
    </div>
  )
}
