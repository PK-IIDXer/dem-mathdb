import { usePageTitle } from '../hooks/usePageTitle'
import { PublicIdRoute } from '../components/PublicIdRoute'
import { Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import { theoremsApi } from '../api/theorems'

/** Shareable public-ID URL for a proof. The route guard rejects internal IDs
 * before querying; a public reference resolves to the proof under its theorem. */
export function ProofPage() {
  return <PublicIdRoute><ProofPageContent /></PublicIdRoute>
}

function ProofPageContent() {
  const { id } = useParams<{ id: string }>()
  const proofRef = id ?? ''
  const { data: proof } = useQuery({ queryKey: ['proofs', proofRef], queryFn: () => proofsApi.get(proofRef) })
  const { data: theorem } = useQuery({
    queryKey: ['theorems', proof?.theorem_id],
    queryFn: () => theoremsApi.get(proof?.theorem_id ?? 0),
    enabled: proof != null,
  })

  usePageTitle(theorem ? `${theorem.name}の証明` : '証明')

  if (!proof || !theorem) return <p className="text-sm text-slate-400">読み込み中…</p>
  return <Navigate to={`/theorems/${theorem.public_id}/proofs/${proof.public_id}`} replace />
}
