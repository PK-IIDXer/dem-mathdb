import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { definitionsApi } from '../api/definitions'
import { FormulaPreview } from '../components/FormulaPreview'
import { DescriptionEditor } from '../components/DescriptionEditor'
import { TagEditor } from '../components/TagEditor'
import { buildDefinitionFormulaSections } from './definitionFormulaSections'

export function DefinitionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const definitionRef = id ?? ''
  const queryClient = useQueryClient()
  const { data: definition } = useQuery({
    queryKey: ['definitions', definitionRef],
    queryFn: () => definitionsApi.get(definitionRef),
  })
  const definitionId = definition?.id ?? 0
  const { data: axiom } = useQuery({
    queryKey: ['definitions', definitionId, 'axiom'],
    queryFn: () => definitionsApi.getAxiom(definitionId),
    enabled: definition != null,
  })
  const { data: formalParams = [] } = useQuery({
    queryKey: ['definitions', definitionId, 'formal-params'],
    queryFn: () => definitionsApi.listFormalParams(definitionId),
    enabled: definition != null,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['definitions'] })
  const setDescriptionMutation = useMutation({
    mutationFn: (description: string | null) => definitionsApi.setDescription(definitionId, description),
    onSuccess: invalidate,
  })
  const addTagMutation = useMutation({
    mutationFn: (tagId: number) => definitionsApi.addTag(definitionId, tagId),
    onSuccess: invalidate,
  })
  const removeTagMutation = useMutation({
    mutationFn: (tagId: number) => definitionsApi.removeTag(definitionId, tagId),
    onSuccess: invalidate,
  })

  if (!definition) return <p className="text-sm text-slate-400">読み込み中…</p>

  const formulaSections = buildDefinitionFormulaSections(
    definition.display_formula?.id ?? null,
    axiom?.formula_id ?? null,
  )

  return (
    <div className="space-y-4">
      <Link to="/definitions" className="text-xs text-indigo-600 hover:underline">
        ← 定義一覧に戻る
      </Link>
      <section className="space-y-4 rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-base text-slate-800">{definition.name}</span>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{definition.kind}</span>
        </div>
        <div className="text-sm">
          <span className="text-xs text-slate-500">new symbol: </span>
          <Link to={`/symbols/${definition.new_symbol.public_id}`} className="font-mono text-indigo-600 hover:underline">
            {definition.new_symbol.name}
          </Link>{' '}
          <span className="text-slate-500">
            ({definition.new_symbol.symbol_type.name}, arity {definition.new_symbol.arity})
          </span>
        </div>
        <div className="text-sm">
          <span className="text-xs text-slate-500">formal params: </span>
          {formalParams.map((p) => p.name).join(', ') || '(none)'}
        </div>
        {formulaSections.map((section) => (
          <div key={section.formulaId}>
            <div className="mb-1 text-xs text-slate-500">
              {section.role === 'readable' ? (
                'readable definition'
              ) : (
                <>
                  {section.role === 'combined' ? 'readable definition / defining axiom: ' : 'defining axiom: '}
                  {axiom && (
                    <Link to={`/axioms/${axiom.public_id}`} className="text-indigo-600 hover:underline">
                      {axiom.name}
                    </Link>
                  )}
                </>
              )}
            </div>
            <div
              className={`overflow-x-auto rounded border px-4 py-4 text-base ${
                section.role === 'axiom' ? 'border-slate-100 bg-white' : 'border-indigo-100 bg-indigo-50/40'
              }`}
            >
              <FormulaPreview formulaId={section.formulaId} />
            </div>
          </div>
        ))}
        {(definition.requires_existence_proof || definition.requires_uniqueness_proof) && (
          <div className="text-xs text-amber-600">
            {definition.requires_existence_proof && '要 存在性証明 '}
            {definition.requires_uniqueness_proof && '要 一意性証明'}
          </div>
        )}
        <div>
          <div className="mb-1 text-xs text-slate-500">description</div>
          <DescriptionEditor
            value={definition.description}
            onSave={(description) => setDescriptionMutation.mutate(description)}
            isSaving={setDescriptionMutation.isPending}
          />
        </div>
        <div>
          <div className="mb-1 text-xs text-slate-500">tags</div>
          <TagEditor
            tags={definition.tags}
            onAdd={(tagId) => addTagMutation.mutate(tagId)}
            onRemove={(tagId) => removeTagMutation.mutate(tagId)}
          />
        </div>
        {definition.remarks && <div className="text-sm text-slate-600">{definition.remarks}</div>}
      </section>

    </div>
  )
}
