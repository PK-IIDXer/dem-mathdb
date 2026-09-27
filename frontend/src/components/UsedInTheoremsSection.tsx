import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Theorem } from '../api/types'

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

interface Props {
  title: string
  queryKey: readonly unknown[]
  queryFn: () => Promise<Theorem[]>
}

/** Reverse-reference list: which theorems' proofs cite this axiom/theorem
 * directly in a step. Not transitive — a theorem that only reaches this one
 * through an intermediate lemma will not appear (see
 * AxiomService.list_used_in_theorems / TheoremService.list_used_in_theorems
 * on the backend). */
export function UsedInTheoremsSection({ title, queryKey, queryFn }: Props) {
  const { data: theorems = [] } = useQuery({ queryKey, queryFn })

  return (
    <div>
      <div className="mb-1 text-xs text-slate-500">
        {title} ({theorems.length})
      </div>
      {theorems.length === 0 ? (
        <p className="text-xs text-slate-400">まだありません</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {theorems.map((theorem) => (
            <li key={theorem.id}>
              <Link to={`/theorems/${theorem.public_id}`} className="text-indigo-600 hover:underline">
                {theorem.name}
              </Link>{' '}
              <span
                className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[theorem.status] ?? ''}`}
              >
                {STATUS_LABEL[theorem.status] ?? theorem.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
