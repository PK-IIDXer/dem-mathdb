import { Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import { theoremsApi } from '../api/theorems'

/** Canonical shareable URL for a proof (`/proofs/:id`). Proofs are always
 * browsed nested under their theorem, so this just redirects there once the
 * theorem_id is known — it exists so links to a bare proof id (e.g. from a
 * "theorem" step's applied_proof_id) always resolve to something. */
export function ProofPage() {
  const { id } = useParams<{ id: string }>()
  const proofRef = id ?? ''
  const { data: proof } = useQuery({ queryKey: ['proofs', proofRef], queryFn: () => proofsApi.get(proofRef) })
  const { data: theorem } = useQuery({
    queryKey: ['theorems', proof?.theorem_id],
    queryFn: () => theoremsApi.get(proof?.theorem_id ?? 0),
    enabled: proof != null,
  })

  if (!proof || !theorem) return <p className="text-sm text-slate-400">読み込み中…</p>
  return <Navigate to={`/theorems/${theorem.public_id}/proofs/${proof.public_id}`} replace />
}
