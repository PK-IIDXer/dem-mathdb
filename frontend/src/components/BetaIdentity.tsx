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
  const beta = useBeta()
  const local = useLocalNamespace()
  const origin = entityOrigin(namespace, local)
  if (!beta || origin == null) return null
  return <span className="ml-2 text-xs text-amber-900">
    <span className="rounded bg-amber-50 px-1.5 py-0.5">{origin === 'base' ? '基本' : '利用者作成（誰でも編集できます）'}</span>
    {detail && origin === 'base' && <span className="ml-2">基本の内容は変更できません。</span>}
  </span>
}

export function UserSymbolNotice({ formulaIds }: { formulaIds: number[] }) {
  const beta = useBeta()
  const local = useLocalNamespace()
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols(), enabled: beta != null })
  const formulas = useQueries({ queries: [...new Set(formulaIds)].map(id => ({ queryKey: ['formulas', id], queryFn: () => formulasApi.get(id), enabled: beta != null, staleTime: Infinity })) })
  if (!beta || !formulas.some(formula => formula.data && hasUserSymbols(formula.data.tokens, symbols, local))) return null
  return <span className="ml-2 text-xs text-amber-800">利用者が作った記号を含みます</span>
}

export function SystemValidityNote({ namespace }: { namespace?: string }) {
  const beta = useBeta()
  const local = useLocalNamespace()
  if (!beta) return null
  return <div className="my-2 text-xs text-amber-900">
    <p>この公理系の公理から証明できることを示します。公理系に矛盾が無いことは示しません。</p>
    {entityOrigin(namespace, local) === 'user' && <p>誰でも公理を追加・削除できます。</p>}
  </div>
}
