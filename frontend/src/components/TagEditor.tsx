import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tagsApi } from '../api/tags'
import { useReadOnly } from '../ReadOnlyContext'
import type { Tag } from '../api/types'

interface Props {
  tags: Tag[]
  onAdd: (tagId: number) => void
  onRemove: (tagId: number) => void
  allowRuleTag?: boolean
}

export function TagEditor({ tags, onAdd, onRemove, allowRuleTag = true }: Props) {
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const { data: allTags = [] } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.list() })
  const [newTagName, setNewTagName] = useState('')

  const attachedIds = new Set(tags.map((t) => t.id))
  const candidates = allTags.filter((t) => !attachedIds.has(t.id) && (allowRuleTag || t.name !== 'system:rule'))

  const createMutation = useMutation({
    mutationFn: (name: string) => tagsApi.getOrCreate(name),
    onSuccess: (tag) => {
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      onAdd(tag.id)
      setNewTagName('')
    },
  })

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag.id}
            className="flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs text-indigo-700"
          >
            {tag.name}
            {!readOnly && (
              <button
                type="button"
                onClick={() => onRemove(tag.id)}
                className="text-indigo-400 hover:text-red-600"
              >
                ×
              </button>
            )}
          </span>
        ))}
        {tags.length === 0 && <span className="text-xs text-slate-400">タグなし</span>}
      </div>
      {!readOnly && (
        <div className="flex items-center gap-1.5">
          <select
            value=""
            onChange={(e) => e.target.value && onAdd(Number(e.target.value))}
            className="rounded border border-slate-300 px-1.5 py-0.5 text-xs"
          >
            <option value="">既存タグを追加…</option>
            {candidates.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
          <input
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            placeholder="新規タグ名"
            className="w-28 rounded border border-slate-300 px-1.5 py-0.5 text-xs"
          />
          <button
            type="button"
            disabled={!newTagName.trim() || createMutation.isPending || (!allowRuleTag && newTagName.trim() === 'system:rule')}
            onClick={() => createMutation.mutate(newTagName.trim())}
            className="rounded bg-slate-600 px-2 py-0.5 text-xs text-white disabled:opacity-40"
          >
            + 作成して追加
          </button>
        </div>
      )}
    </div>
  )
}
