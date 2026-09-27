import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { FormulaPreview } from './FormulaPreview'
import type { Theorem } from '../api/types'

export function InferenceRulePicker({ onChoose, selectedId, testId }: {
  onChoose: (theorem: Theorem) => void
  selectedId?: number | ''
  testId?: string
}) {
  const { data: rules = [], isPending } = useQuery({
    queryKey: ['theorems', 'rules', 'picker'],
    queryFn: async () => {
      const theorems = await theoremsApi.listRules()
      return Promise.all(theorems.map(async (theorem) => ({
        theorem,
        premiseCount: (await theoremsApi.listPremises(theorem.id)).length,
      })))
    },
    staleTime: 0,
  })
  return (
    <div data-testid={testId} className="space-y-1 rounded border border-indigo-100 bg-indigo-50 p-2">
      {isPending && <p className="text-xs text-slate-500">推論定理を読み込み中…</p>}
      {!isPending && rules.length === 0 && <p className="text-xs text-slate-500">利用できる推論定理はありません</p>}
      {rules.map(({ theorem, premiseCount }) => (
        <button
          key={theorem.id}
          type="button"
          onClick={() => onChoose(theorem)}
          className={`block w-full rounded px-2 py-1 text-left text-xs hover:bg-indigo-100 ${selectedId === theorem.id ? 'bg-indigo-200' : 'bg-white'}`}
        >
          <span className="font-semibold">{theorem.name}</span>
          <span className="ml-2 text-slate-500">前提 {premiseCount} 件</span>
          <span className="ml-2 text-slate-600">結論: <FormulaPreview formulaId={theorem.conclusion_formula_id} /></span>
        </button>
      ))}
    </div>
  )
}
