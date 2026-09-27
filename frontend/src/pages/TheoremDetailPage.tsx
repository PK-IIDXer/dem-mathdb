import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { proofsApi } from '../api/proofs'
import { ProofDetail } from '../components/ProofDetail'
import { TheoremStatement } from '../components/TheoremStatement'
import { DescriptionEditor } from '../components/DescriptionEditor'
import { TagEditor } from '../components/TagEditor'
import { UsedInTheoremsSection } from '../components/UsedInTheoremsSection'
import { DependencyGraph } from '../components/DependencyGraph'
import { useReadOnly } from '../ReadOnlyContext'
import { theoremVariableContext } from '../theoremContext'
import { OnboardingCoach } from '../components/OnboardingCoach'
import { onboardingQuery } from '../onboarding'
import { tagsApi } from '../api/tags'

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}
const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

export function TheoremDetailPage() {
  const readOnly = useReadOnly()
  const { id, proofId: proofIdParam } = useParams<{ id: string; proofId?: string }>()
  const theoremRef = id ?? ''
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const onboarding = searchParams.get('onboarding') === '1'
  const queryClient = useQueryClient()

  const { data: theorem } = useQuery({
    queryKey: ['theorems', theoremRef],
    queryFn: () => theoremsApi.get(theoremRef),
  })
  const theoremId = theorem?.id ?? 0
  const { data: proofs = [] } = useQuery({
    queryKey: ['theorems', theoremId, 'proofs'],
    queryFn: () => proofsApi.listForTheorem(theoremId),
    enabled: theorem != null,
  })
  const selectedProof = proofs.find(
    (proof) => proof.public_id === proofIdParam || String(proof.id) === proofIdParam,
  )
  const proofId = selectedProof?.id ?? null
  const verifiedProof = proofs.find((proof) => proof.status === 'verified')
  // Onboarding ends once the theorem is proven; later proofs are ordinary proofs, not coached ones.
  const onboardingComplete = theorem?.status === 'proven' || verifiedProof != null
  const variableContext = useMemo(
    () => theoremVariableContext(theorem?.remarks ?? null),
    [theorem?.remarks],
  )

  const invalidateTheorem = () => queryClient.invalidateQueries({ queryKey: ['theorems'] })
  const setDescriptionMutation = useMutation({
    mutationFn: (description: string | null) => theoremsApi.setDescription(theoremId, description),
    onSuccess: invalidateTheorem,
  })
  const addTagMutation = useMutation({
    mutationFn: (tagId: number) => theoremsApi.addTag(theoremId, tagId),
    onSuccess: invalidateTheorem,
  })
  const removeTagMutation = useMutation({
    mutationFn: (tagId: number) => theoremsApi.removeTag(theoremId, tagId),
    onSuccess: invalidateTheorem,
  })
  const markedAsRule = theorem?.tags.find((tag) => tag.name === 'system:rule')
  const toggleRuleMutation = useMutation({
    mutationFn: async () => {
      if (markedAsRule) return theoremsApi.removeTag(theoremId, markedAsRule.id)
      const tag = await tagsApi.getOrCreate('system:rule')
      return theoremsApi.addTag(theoremId, tag.id)
    },
    onSuccess: invalidateTheorem,
  })

  const createProofMutation = useMutation({
    mutationFn: () => proofsApi.create({ theorem_id: theoremId }),
    onSuccess: (proof) => {
      queryClient.invalidateQueries({ queryKey: ['theorems', theoremId, 'proofs'] })
      navigate(`/theorems/${theorem?.public_id}/proofs/${proof.public_id}${onboarding && !onboardingComplete ? onboardingQuery() : ''}`)
    },
  })

  if (!theorem) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <div className="space-y-6">
      <Link to="/search" className="text-xs text-indigo-600 hover:underline">
        ← 検索に戻る
      </Link>

      <section className="space-y-4 rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-base text-slate-800">{theorem.name}</span>
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_BADGE[theorem.status] ?? ''}`}>
            {STATUS_LABEL[theorem.status] ?? theorem.status}
          </span>
        </div>

        <TheoremStatement theoremId={theoremId} context={variableContext} />
        {Object.keys(variableContext).length > 0 && (
          <div className="text-xs text-slate-500">
            変数: {Object.keys(variableContext).join(', ')}
          </div>
        )}

        <div>
          <div className="mb-1 text-xs text-slate-500">description</div>
          <DescriptionEditor
            value={theorem.description}
            onSave={(description) => setDescriptionMutation.mutate(description)}
            isSaving={setDescriptionMutation.isPending}
          />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-500">tags</div>
          <TagEditor
            tags={theorem.tags}
            onAdd={(tagId) => addTagMutation.mutate(tagId)}
            onRemove={(tagId) => removeTagMutation.mutate(tagId)}
            allowRuleTag={theorem.status === 'proven' && verifiedProof != null}
          />
          {markedAsRule && <p className="mt-1 text-xs text-indigo-700">推論定理の印あり{verifiedProof == null ? '（verified proof がないため候補には表示しません）' : ''}</p>}
          {!readOnly && theorem.status === 'proven' && verifiedProof != null && (
            <button type="button" disabled={toggleRuleMutation.isPending} onClick={() => toggleRuleMutation.mutate()} className="mt-2 rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 disabled:opacity-40">
              {markedAsRule ? '推論定理の印を外す' : '推論定理として印を付ける'}
            </button>
          )}
        </div>
        <UsedInTheoremsSection
          title="この定理を補題として使っている定理"
          queryKey={['theorems', theoremId, 'used-in-theorems']}
          queryFn={() => theoremsApi.listUsedInTheorems(theoremId)}
        />
      </section>

      <section className="rounded-lg border border-slate-200 p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">Proof ({proofs.length})</h3>
          {!readOnly && (
            <button
              type="button"
              disabled={createProofMutation.isPending}
              onClick={() => createProofMutation.mutate()}
              className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              新規 Proof を作成
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {proofs.map((proof) => (
            <Link
              key={proof.id}
              to={`/theorems/${theorem.public_id}/proofs/${proof.public_id}`}
              className={`rounded px-2 py-1 text-xs ${
                proofId === proof.id ? 'bg-indigo-600 text-white' : 'bg-slate-100 hover:bg-slate-200'
              }`}
            >
              #{proof.id} {proof.name ?? '(no name)'} — {proof.status}
            </Link>
          ))}
          {proofs.length === 0 && <span className="text-xs text-slate-400">まだありません</span>}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">依存関係</h3>
        <DependencyGraph theoremId={theoremId} />
      </section>

      {proofId != null && (
        <ProofDetail
          proofId={proofId}
          theoremId={theoremId}
          context={variableContext}
          onboarding={onboarding && (!onboardingComplete || selectedProof?.status === 'verified')}
        />
      )}

      {onboarding && proofId == null && onboardingComplete && (
        <OnboardingCoach step={3} title="検証されました">
          <p className="font-semibold text-green-700">✓ この定理はすでに証明済みです。</p>
          {verifiedProof && (
            <Link
              to={`/theorems/${theorem.public_id}/proofs/${verifiedProof.public_id}${onboardingQuery()}`}
              className="inline-block rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white"
            >
              検証済みの Proof #{verifiedProof.id} を見る
            </Link>
          )}
        </OnboardingCoach>
      )}

      {onboarding && proofId == null && !onboardingComplete && (
        <OnboardingCoach step={3} title="証明する">
          <p>表示されている結論が「あと何を示すか」です。［新規 Proof を作成］を押してください。</p>
          <p>作成後もこの実物の定理画面で、公理検索と MP の提案を使って証明します。</p>
        </OnboardingCoach>
      )}

    </div>
  )
}
