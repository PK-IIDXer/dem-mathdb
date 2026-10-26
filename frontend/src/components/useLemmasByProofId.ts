import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import type { LemmaDependency } from '../api/types'

export function useLemmasByProofId(proofId: number, enabled: boolean) {
  const { data: directDependencies } = useQuery({
    queryKey: ['proofs', proofId, 'direct-dependencies'],
    queryFn: () => proofsApi.listDirectDependencies(proofId),
    enabled,
  })
  return useMemo(() => {
    const byTheorem = new Map((directDependencies?.lemmas ?? []).map((lemma) => [lemma.theorem.id, lemma]))
    const byProof = new Map<number, LemmaDependency>()
    for (const [appliedProofId, theoremId] of Object.entries(directDependencies?.applied_proofs ?? {})) {
      const lemma = byTheorem.get(theoremId)
      if (lemma) byProof.set(Number(appliedProofId), { ...lemma, proof_id: Number(appliedProofId), proof_public_id: directDependencies?.applied_proof_public_ids?.[appliedProofId] })
    }
    for (const lemma of directDependencies?.lemmas ?? []) byProof.set(lemma.proof_id, { ...lemma, proof_public_id: directDependencies?.applied_proof_public_ids?.[lemma.proof_id] })
    return byProof
  }, [directDependencies])
}
