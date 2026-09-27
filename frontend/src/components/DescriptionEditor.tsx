import { useEffect, useState } from 'react'
import { useReadOnly } from '../ReadOnlyContext'

interface Props {
  value: string | null
  onSave: (description: string | null) => void
  isSaving?: boolean
}

export function DescriptionEditor({ value, onSave, isSaving }: Props) {
  const readOnly = useReadOnly()
  const [draft, setDraft] = useState(value ?? '')

  useEffect(() => setDraft(value ?? ''), [value])

  const dirty = draft !== (value ?? '')

  if (readOnly) {
    return (
      <p className="text-sm text-slate-600">
        {value || <span className="text-slate-400">(説明なし)</span>}
      </p>
    )
  }

  return (
    <div className="space-y-1">
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="自然言語での説明 (例: 空集合の存在公理)"
        rows={2}
        className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
      />
      {dirty && (
        <button
          type="button"
          disabled={isSaving}
          onClick={() => onSave(draft.trim() === '' ? null : draft)}
          className="rounded bg-slate-600 px-2 py-1 text-xs text-white disabled:opacity-40"
        >
          保存
        </button>
      )}
    </div>
  )
}
