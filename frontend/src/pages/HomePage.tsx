import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { tagsApi } from '../api/tags'
import { axiomsApi } from '../api/axioms'
import { FormulaPreview } from '../components/FormulaPreview'
import { ONBOARDING_TAG_NAME, onboardingQuery } from '../onboarding'
import { useReadOnly } from '../ReadOnlyContext'

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

const RECENT_COUNT = 5

export function HomePage() {
  const readOnly = useReadOnly()
  const { data: theorems = [] } = useQuery({ queryKey: ['theorems'], queryFn: () => theoremsApi.listVisible() })
  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.list() })
  const { data: axiomSystems = [] } = useQuery({ queryKey: ['axiomSystems'], queryFn: () => axiomsApi.listSystems() })

  const provenCount = theorems.filter((t) => t.status === 'proven').length
  const conjectureCount = theorems.length - provenCount
  const recentTheorems = [...theorems].sort((a, b) => b.id - a.id).slice(0, RECENT_COUNT)
  const visibleTags = tags.filter((tag) => tag.name !== ONBOARDING_TAG_NAME)

  return (
    <div className="space-y-6">
      {!readOnly && (
        <section className="rounded-xl border border-indigo-200 bg-indigo-50 p-5">
          <h2 className="text-lg font-semibold text-indigo-950">はじめての定理</h2>
          <p className="mt-1 text-sm text-indigo-900">実際の画面で、式の入力から機械検証済みの証明まで進めます。</p>
          <Link
            to={`/formulas${onboardingQuery()}`}
            className="mt-3 inline-block rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            定理を 1 本書く
          </Link>
        </section>
      )}
      <section className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-slate-200 p-4 text-center">
          <div className="text-2xl font-bold text-slate-800">{theorems.length}</div>
          <div className="text-xs text-slate-500">登録済みの定理</div>
        </div>
        <div className="rounded-lg border border-slate-200 p-4 text-center">
          <div className="text-2xl font-bold text-green-700">{provenCount}</div>
          <div className="text-xs text-slate-500">証明済み</div>
        </div>
        <div className="rounded-lg border border-slate-200 p-4 text-center">
          <div className="text-2xl font-bold text-slate-600">{conjectureCount}</div>
          <div className="text-xs text-slate-500">未証明</div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">最近の定理</h2>
          <Link to="/search" className="text-xs text-indigo-600 hover:underline">
            すべての定理を探す →
          </Link>
        </div>
        {recentTheorems.length === 0 ? (
          <p className="text-sm text-slate-400">まだ定理が登録されていません</p>
        ) : (
          <ul className="space-y-2">
            {recentTheorems.map((theorem) => (
              <li key={theorem.id}>
                <Link
                  to={`/theorems/${theorem.public_id}`}
                  className="block rounded border border-slate-100 px-3 py-2 hover:border-indigo-300 hover:bg-indigo-50/40"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-sm text-slate-800">{theorem.name}</span>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[theorem.status] ?? ''}`}
                    >
                      {STATUS_LABEL[theorem.status] ?? theorem.status}
                    </span>
                  </div>
                  <div className="text-sm">
                    <FormulaPreview formulaId={theorem.conclusion_formula_id} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-slate-200 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">タグ</h2>
          {visibleTags.length === 0 ? (
            <p className="text-sm text-slate-400">タグはまだありません</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {visibleTags.map((tag) => (
                <Link
                  key={tag.id}
                  to={`/search?tags=${tag.id}`}
                  className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  {tag.name}
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">公理系</h2>
          {axiomSystems.length === 0 ? (
            <p className="text-sm text-slate-400">公理系はまだありません</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {axiomSystems.map((system) => (
                <li key={system.id}>
                  <Link to={`/axiom-systems/${system.id}`} className="text-indigo-600 hover:underline">
                    {system.name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
