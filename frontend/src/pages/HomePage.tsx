import { configApi } from '../api/config'
import { EntityBadge } from '../components/BetaIdentity'
import { statsApi } from '../api/stats'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { tagsApi } from '../api/tags'
import { axiomsApi } from '../api/axioms'
import { FormulaPreview } from '../components/FormulaPreview'
import { ONBOARDING_TAG_NAME, onboardingQuery } from '../onboarding'
import { EXPLORATION_TAG_NAME } from '../exploration'
import { useReadOnly } from '../ReadOnlyContext'
import { BetaGettingStarted } from '../components/BetaGettingStarted'
import { useBeta } from '../components/BetaContext'

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
  usePageTitle('')
  const readOnly = useReadOnly()
  const beta = useBeta()
  const { isSuccess: configured } = useQuery({ queryKey: ['config'], queryFn: configApi.get, enabled: false })
  const { data: theorems = [] } = useQuery({ queryKey: ['theorems'], queryFn: () => theoremsApi.listVisible() })
  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.list() })
  const { data: axiomSystems = [] } = useQuery({ queryKey: ['axiomSystems'], queryFn: () => axiomsApi.listSystems() })

  const { data: stats, isError: statsError } = useQuery({ queryKey: ['stats'], queryFn: statsApi.get })
  const recentTheorems = [...theorems].sort((a, b) => b.id - a.id).slice(0, RECENT_COUNT)
  const visibleTags = tags.filter(
    (tag) => tag.name !== ONBOARDING_TAG_NAME && tag.name !== EXPLORATION_TAG_NAME,
  )

  return (
    <div className="space-y-6">
      <BetaGettingStarted theorems={theorems} />
      {!readOnly && !beta && configured && (
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
      <section aria-label="収録規模" className="grid grid-cols-3 gap-3">
        {([
          ['theorem_count', '登録済みの定理'],
          ['proven_theorem_count', '証明済み'],
          ['proof_step_count', '証明ステップ'],
          ['primitive_axiom_count', '原始公理'],
          ['axiom_system_count', '公理系'],
          ['dependency_count', '定理間の依存'],
        ] as const).map(([key, label]) => (
          <div key={key} className="rounded-lg border border-slate-200 p-4 text-center">
            <div className="text-2xl font-bold text-slate-800">{stats?.[key].toLocaleString('ja-JP') ?? '—'}</div>
            <div className="text-xs text-slate-500">{label}</div>
          </div>
        ))}
      </section>
      {beta && <p className="text-xs text-slate-500">定理とその証明・依存の件数は、練習の定理と推論ノートを除いた数です。</p>}
      {statsError && <p role="alert" className="text-sm text-slate-500">収録規模を取得できませんでした。</p>}

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
                    <span className="font-mono text-sm text-slate-800">{theorem.name}</span> <EntityBadge namespace={theorem.namespace_name} />
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
                  <Link to={`/axiom-systems/${system.public_id}`} className="text-indigo-600 hover:underline">
                    {system.name}
                  </Link> <EntityBadge namespace={system.namespace_name} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
