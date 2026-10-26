import { SystemValidityNote } from '../components/BetaIdentity'
import { EntityBadge } from '../components/BetaIdentity'
import { usePageTitle } from '../hooks/usePageTitle'
import { PublicIdRoute } from '../components/PublicIdRoute'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

export function AxiomSystemDetailPage() {
  return <PublicIdRoute><AxiomSystemDetailContent /></PublicIdRoute>
}

function AxiomSystemDetailContent() {
  const { id } = useParams<{ id: string }>()
  const systemRef = id ?? ''

  const { data: system } = useQuery({
    queryKey: ['axiomSystems', systemRef],
    queryFn: () => axiomsApi.getSystem(systemRef),
  })
  const systemId = system?.id ?? 0
  const { data: members = [] } = useQuery({
    queryKey: ['axiomSystemMembers', systemId],
    queryFn: () => axiomsApi.listSystemMembers(systemId),
    enabled: system != null,
  })
  const { data: theorems = [] } = useQuery({
    queryKey: ['axiomSystems', systemId, 'theorems'],
    queryFn: () => axiomsApi.listSystemProvableTheorems(systemId),
    enabled: system != null,
  })

  usePageTitle(system?.name ?? '公理系')

  if (!system) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <div className="space-y-4">
      <Link to="/axioms" className="text-xs text-indigo-600 hover:underline">
        ← 公理一覧に戻る
      </Link>

      <SystemValidityNote namespace={system.namespace_name} />
      <section className="space-y-3 rounded-lg border border-slate-200 p-4">
        <span className="font-mono text-base text-slate-800">{system.name}</span> <EntityBadge namespace={system.namespace_name} detail />
        {system.remarks && <div className="text-sm text-slate-600">{system.remarks}</div>}
        <div>
          <div className="mb-1 text-xs text-slate-500">メンバー公理 ({members.length})</div>
          {members.length === 0 ? (
            <p className="text-xs text-slate-400">メンバーなし</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {members.map((axiom) => (
                <li key={axiom.id}>
                  <Link
                    to={`/axioms/${axiom.public_id}`}
                    className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs text-indigo-700 hover:bg-indigo-100"
                  >
                    {axiom.name}
                  </Link> <EntityBadge namespace={axiom.namespace_name} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 p-4">
        <div className="mb-2 text-sm font-semibold text-slate-700">この公理系で成立する定理 ({theorems.length})</div>
        {theorems.length === 0 ? (
          <p className="text-xs text-slate-400">まだありません</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {theorems.map((theorem) => (
              <li key={theorem.id}>
                <Link to={`/theorems/${theorem.public_id}`} className="text-indigo-600 hover:underline">
                  {theorem.name}
                </Link> <EntityBadge namespace={theorem.namespace_name} />{' '}
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[theorem.status] ?? ''}`}
                >
                  {STATUS_LABEL[theorem.status] ?? theorem.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
