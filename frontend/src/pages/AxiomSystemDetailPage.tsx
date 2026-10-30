import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { SystemValidityNote } from '../components/BetaIdentity'
import { EntityBadge } from '../components/BetaIdentity'
import { usePageTitle } from '../hooks/usePageTitle'
import { PublicIdRoute } from '../components/PublicIdRoute'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'

const STATUS_LABEL: Record<string, string> = {
  get conjecture() { return t("DependencyGraph_125") },
  get proven() { return t("DependencyGraph_126") },
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

export function AxiomSystemDetailPage() {
  useLanguage()

  return <PublicIdRoute><AxiomSystemDetailContent /></PublicIdRoute>
}

function AxiomSystemDetailContent() {
  useLanguage()

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

  usePageTitle(system?.name ?? t("AxiomSystemDetailPage_499"))

  if (!system) return <p className="text-sm text-slate-400">{t("BetaGettingStarted_109")}</p>

  return (
    <div className="space-y-4">
      <Link to="/axioms" className="text-xs text-indigo-600 hover:underline">
        {t("AxiomDetailPage_478")}</Link>

      <SystemValidityNote namespace={system.namespace_name} />
      <section className="space-y-3 rounded-lg border border-slate-200 p-4">
        <span className="font-mono text-base text-slate-800">{system.name}</span> <EntityBadge namespace={system.namespace_name} detail />
        {system.remarks && <div className="text-sm text-slate-600">{system.remarks}</div>}
        <div>
          <div className="mb-1 text-xs text-slate-500">{t("AxiomSystemDetailPage_502")}{members.length})</div>
          {members.length === 0 ? (
            <p className="text-xs text-slate-400">{t("AxiomsPage_492")}</p>
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
        <div className="mb-2 text-sm font-semibold text-slate-700">{t("AxiomSystemDetailPage_504")}{theorems.length})</div>
        {theorems.length === 0 ? (
          <p className="text-xs text-slate-400">{t("AxiomSystemDetailPage_505")}</p>
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
