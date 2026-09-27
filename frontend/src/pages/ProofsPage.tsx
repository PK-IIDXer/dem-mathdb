import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { proofsApi } from '../api/proofs'
import { useReadOnly } from '../ReadOnlyContext'

export function ProofsPage() {
  const readOnly = useReadOnly()
  const navigate = useNavigate()
  const { data: theorems = [] } = useQuery({ queryKey: ['theorems'], queryFn: () => theoremsApi.listVisible() })
  const [theoremId, setTheoremId] = useState<number | ''>('')
  const selectedTheorem = theorems.find((theorem) => theorem.id === theoremId)

  const { data: proofs = [] } = useQuery({
    queryKey: ['theorems', theoremId, 'proofs'],
    queryFn: () => proofsApi.listForTheorem(Number(theoremId)),
    enabled: theoremId !== '',
  })

  const createProofMutation = useMutation({
    mutationFn: () => proofsApi.create({ theorem_id: Number(theoremId) }),
    onSuccess: (proof) => navigate(`/theorems/${selectedTheorem?.public_id}/proofs/${proof.public_id}`),
  })

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">対象の定理を選ぶ</h2>
        <div className="flex items-center gap-2">
          <select
            value={theoremId}
            onChange={(e) => setTheoremId(Number(e.target.value))}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>
              選択…
            </option>
            {theorems.map((theorem) => (
              <option key={theorem.id} value={theorem.id}>
                {theorem.name} ({theorem.status})
              </option>
            ))}
          </select>
          {!readOnly && (
            <button
              type="button"
              disabled={theoremId === '' || createProofMutation.isPending}
              onClick={() => createProofMutation.mutate()}
              className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              新規 Proof を作成
            </button>
          )}
        </div>

        {theoremId !== '' && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-slate-500">既存の Proof ({proofs.length})</div>
            <div className="flex flex-wrap gap-2">
              {proofs.map((proof) => (
                <Link
                  key={proof.id}
                  to={`/theorems/${selectedTheorem?.public_id}/proofs/${proof.public_id}`}
                  className="rounded bg-slate-100 px-2 py-1 text-xs hover:bg-slate-200"
                >
                  #{proof.id} {proof.name ?? '(no name)'} — {proof.status}
                </Link>
              ))}
              {proofs.length === 0 && <span className="text-xs text-slate-400">まだありません</span>}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
