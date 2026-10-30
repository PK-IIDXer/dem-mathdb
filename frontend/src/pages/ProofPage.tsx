import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { usePageTitle } from '../hooks/usePageTitle'
import { PublicIdRoute } from '../components/PublicIdRoute'
import { Navigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import { theoremsApi } from '../api/theorems'

/** Shareable public-ID URL for a proof. The route guard rejects internal IDs
 * before querying; a public reference resolves to the proof under its theorem. */
export function ProofPage() {
  useLanguage()

  return <PublicIdRoute><ProofPageContent /></PublicIdRoute>
}

function ProofPageContent() {
  useLanguage()

  const { id } = useParams<{ id: string }>()
  const proofRef = id ?? ''
  const { data: proof } = useQuery({ queryKey: ['proofs', proofRef], queryFn: () => proofsApi.get(proofRef) })
  const { data: theorem } = useQuery({
    queryKey: ['theorems', proof?.theorem_id],
    queryFn: () => theoremsApi.get(proof?.theorem_id ?? 0),
    enabled: proof != null,
  })

  usePageTitle(theorem ? t("CommandPalette_038", theorem.name) : t("ProofDetail_248"))

  if (!proof || !theorem) return <p className="text-sm text-slate-400">{t("BetaGettingStarted_109")}</p>
  return <Navigate to={`/theorems/${theorem.public_id}/proofs/${proof.public_id}`} replace />
}
