import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'
import { FormulaPreview } from '../components/FormulaPreview'
import { DescriptionEditor } from '../components/DescriptionEditor'
import { TagEditor } from '../components/TagEditor'
import { UsedInTheoremsSection } from '../components/UsedInTheoremsSection'

export function AxiomDetailPage() {
  const { id } = useParams<{ id: string }>()
  const axiomRef = id ?? ''
  const queryClient = useQueryClient()
  const { data: axiom } = useQuery({ queryKey: ['axioms', axiomRef], queryFn: () => axiomsApi.get(axiomRef) })
  const axiomId = axiom?.id ?? 0

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['axioms'] })
  const setDescriptionMutation = useMutation({
    mutationFn: (description: string | null) => axiomsApi.setDescription(axiomId, description),
    onSuccess: invalidate,
  })
  const addTagMutation = useMutation({
    mutationFn: (tagId: number) => axiomsApi.addTag(axiomId, tagId),
    onSuccess: invalidate,
  })
  const removeTagMutation = useMutation({
    mutationFn: (tagId: number) => axiomsApi.removeTag(axiomId, tagId),
    onSuccess: invalidate,
  })

  if (!axiom) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <div className="space-y-4">
      <Link to="/axioms" className="text-xs text-indigo-600 hover:underline">
        ← 公理一覧に戻る
      </Link>
      <section className="space-y-4 rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-base text-slate-800">{axiom.name}</span>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{axiom.origin_kind}</span>
        </div>
        <div className="overflow-x-auto rounded border border-slate-100 bg-white px-4 py-4 text-base">
          <FormulaPreview formulaId={axiom.formula_id} />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-500">description</div>
          <DescriptionEditor
            value={axiom.description}
            onSave={(description) => setDescriptionMutation.mutate(description)}
            isSaving={setDescriptionMutation.isPending}
          />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-500">tags</div>
          <TagEditor
            tags={axiom.tags}
            onAdd={(tagId) => addTagMutation.mutate(tagId)}
            onRemove={(tagId) => removeTagMutation.mutate(tagId)}
          />
        </div>
        {axiom.remarks && <div className="text-sm text-slate-600">{axiom.remarks}</div>}
        <UsedInTheoremsSection
          title="この公理を使っている定理"
          queryKey={['axioms', axiomId, 'used-in-theorems']}
          queryFn={() => axiomsApi.listUsedInTheorems(axiomId)}
        />
      </section>
    </div>
  )
}
