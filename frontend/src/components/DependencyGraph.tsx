import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import type { DirectDependencies, LemmaDependency } from '../api/types'

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

/** Direct (non-transitive) axiom and lemma-theorem dependencies of one proof,
 * with each lemma's name and status — the one-hop building block for the
 * click-to-expand tree below, fetched in a single request. */
function useDirectDependencies(proofId: number | null) {
  return useQuery({
    queryKey: ['proofs', proofId, 'direct-dependencies'],
    queryFn: () => proofsApi.listDirectDependencies(proofId!),
    enabled: proofId != null,
  })
}

function DependencyItems({
  dependencies,
  ancestorIds,
}: {
  dependencies: DirectDependencies
  ancestorIds: ReadonlySet<number>
}) {
  return (
    <>
      {dependencies.axioms.map((axiom) => (
        <li key={`axiom-${axiom.id}`} className="text-xs">
          <Link to={`/axioms/${axiom.id}`} className="text-slate-500 hover:text-indigo-600 hover:underline">
            公理 {axiom.name}
          </Link>
        </li>
      ))}
      {dependencies.lemmas
        .filter((lemma) => !ancestorIds.has(lemma.theorem.id))
        .map((lemma) => (
          <DependencyNode key={lemma.theorem.id} lemma={lemma} ancestorIds={ancestorIds} />
        ))}
    </>
  )
}

/** Only mounted while its parent node is expanded, so a collapsed node never
 * fetches its own dependencies. The lemma's applied proof is always verified,
 * so its dependencies can be read from it directly. */
function DependencyChildren({ proofId, ancestorIds }: { proofId: number; ancestorIds: ReadonlySet<number> }) {
  const { data: dependencies } = useDirectDependencies(proofId)
  if (!dependencies) return <li className="text-xs text-slate-400">読み込み中…</li>
  const hasChildren =
    dependencies.axioms.length > 0 || dependencies.lemmas.some((lemma) => !ancestorIds.has(lemma.theorem.id))
  if (!hasChildren) return <li className="text-xs text-slate-400">依存なし</li>
  return <DependencyItems dependencies={dependencies} ancestorIds={ancestorIds} />
}

function DependencyNode({ lemma, ancestorIds }: { lemma: LemmaDependency; ancestorIds: ReadonlySet<number> }) {
  const [expanded, setExpanded] = useState(false)
  const { theorem } = lemma

  return (
    <li>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={`${theorem.name} の依存関係`}
          className="w-4 text-xs text-slate-400 hover:text-slate-600"
        >
          {expanded ? '▾' : '▸'}
        </button>
        <Link to={`/theorems/${theorem.id}`} className="font-mono text-sm text-indigo-600 hover:underline">
          {theorem.name}
        </Link>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[theorem.status] ?? ''}`}>
          {STATUS_LABEL[theorem.status] ?? theorem.status}
        </span>
      </div>
      {expanded && (
        <ul className="ml-5 mt-1 space-y-1 border-l border-slate-100 py-1 pl-3">
          <DependencyChildren proofId={lemma.proof_id} ancestorIds={new Set([...ancestorIds, theorem.id])} />
        </ul>
      )}
    </li>
  )
}

/** Click-to-expand dependency tree rooted at a theorem: shows the axioms and
 * lemma theorems its verified proof cites directly, one hop at a time. Each
 * lemma theorem can be expanded further to see what it in turn depends on.
 * Cycle-safe by construction (a proof can only cite already-verified
 * proofs), but ancestorIds guards against it defensively regardless. */
export function DependencyGraph({ theoremId }: { theoremId: number }) {
  // Same key as the theorem page's proof list, so this is normally a cache hit.
  const { data: proofs } = useQuery({
    queryKey: ['theorems', theoremId, 'proofs'],
    queryFn: () => proofsApi.listForTheorem(theoremId),
  })
  const verifiedProof = proofs?.find((p) => p.status === 'verified') ?? null
  const { data: dependencies } = useDirectDependencies(verifiedProof?.id ?? null)

  if (!proofs) return <p className="text-xs text-slate-400">読み込み中…</p>
  if (!verifiedProof) {
    return <p className="text-xs text-slate-400">検証済みの証明がないため、依存関係を表示できません。</p>
  }
  if (!dependencies) return <p className="text-xs text-slate-400">読み込み中…</p>
  if (dependencies.axioms.length === 0 && dependencies.lemmas.length === 0) {
    return <p className="text-xs text-slate-400">依存する公理・定理はありません。</p>
  }

  return (
    <ul className="space-y-1">
      <DependencyItems dependencies={dependencies} ancestorIds={new Set([theoremId])} />
    </ul>
  )
}
