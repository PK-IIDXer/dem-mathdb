import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useQueries, useQuery } from '@tanstack/react-query'
import { workspaceApi } from '../api/workspace'
import { symbolsApi } from '../api/symbols'
import { formulasApi } from '../api/formulas'
import { useBeta } from './BetaContext'
import { entityOrigin, hasUserSymbols } from './betaIdentityModel'

function useLocalNamespace() {
  const beta = useBeta()
  const { data } = useQuery({ queryKey: ['workspace', 'info'], queryFn: () => workspaceApi.info(), enabled: beta != null, staleTime: Infinity })
  return beta ? data?.local_namespace_name : undefined
}

export function EntityBadge({ namespace, detail = false }: { namespace?: string; detail?: boolean }) {
  useLanguage()

  const beta = useBeta()
  const local = useLocalNamespace()
  const origin = entityOrigin(namespace, local)
  if (!beta || origin == null) return null
  return <span className="ml-2 text-xs text-amber-900">
    <span className="rounded bg-amber-50 px-1.5 py-0.5">{origin === 'base' ? t("BetaIdentity_118") : t("BetaIdentity_119")}</span>
    {detail && origin === 'base' && <span className="ml-2">{t("BetaIdentity_120")}</span>}
  </span>
}

export function UserSymbolNotice({ formulaIds }: { formulaIds: number[] }) {
  useLanguage()

  const beta = useBeta()
  const local = useLocalNamespace()
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols(), enabled: beta != null })
  const formulas = useQueries({ queries: [...new Set(formulaIds)].map(id => ({ queryKey: ['formulas', id], queryFn: () => formulasApi.get(id), enabled: beta != null, staleTime: Infinity })) })
  if (!beta || !formulas.some(formula => formula.data && hasUserSymbols(formula.data.tokens, symbols, local))) return null
  return <span className="ml-2 text-xs text-amber-800">{t("BetaIdentity_121")}</span>
}

export function SystemValidityNote({ namespace }: { namespace?: string }) {
  useLanguage()

  const beta = useBeta()
  const local = useLocalNamespace()
  if (!beta) return null
  return <div className="my-2 text-xs text-amber-900">
    <p>{t("BetaIdentity_122")}</p>
    {entityOrigin(namespace, local) === 'user' && <p>{t("BetaIdentity_123")}</p>}
  </div>
}
