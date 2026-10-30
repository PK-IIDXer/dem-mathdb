import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useId, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { tagsApi } from '../api/tags'
import type { Tag } from '../api/types'
import { ONBOARDING_TAG_NAME } from '../onboarding'
import { EXPLORATION_TAG_NAME } from '../exploration'
import { isImeEvent, useCommand } from '../commands/CommandProvider'

interface Props {
  search: string
  onSearchChange: (value: string) => void
  selectedTagIds: number[]
  onToggleTag: (tagId: number) => void
  placeholder?: string
}

const NO_TAGS: Tag[] = []

export function SearchFilterBar({ search, onSearchChange, selectedTagIds, onToggleTag, placeholder }: Props) {
  useLanguage()

  const searchRef = useRef<HTMLInputElement>(null)
  const { data: tags = NO_TAGS } = useQuery({ queryKey: ['tags'], queryFn: () => tagsApi.list() })
  useCommand('search.focus', () => searchRef.current?.focus())

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-3">
      <input
        ref={searchRef}
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder={placeholder ?? t("SearchFilterBar_363")}
        className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
      />
      <span className="block text-right text-[10px] text-slate-400">{t("SearchFilterBar_364")}<kbd>/</kbd></span>
      <TagPicker tags={tags} selectedTagIds={selectedTagIds} onToggleTag={onToggleTag} />
    </div>
  )
}

function TagPicker({
  tags,
  selectedTagIds,
  onToggleTag,
}: {
  tags: Tag[]
  selectedTagIds: number[]
  onToggleTag: (tagId: number) => void
}) {
  useLanguage()

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const composingRef = useRef(false)
  const listboxId = useId()
  const availableTags = useMemo(
    () => tags
      .filter((tag) => tag.name !== ONBOARDING_TAG_NAME && tag.name !== EXPLORATION_TAG_NAME)
      .filter((tag) => tag.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())),
    [query, tags],
  )
  const selectedTags = tags.filter((tag) => selectedTagIds.includes(tag.id))
  if (tags.length === 0) return null
  return (
    <div className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => setOpen((value) => !value)}
        className="rounded border border-slate-300 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
      >
        {t("SearchFilterBar_365")}{selectedTagIds.length > 0 ? t("SearchFilterBar_366", selectedTagIds.length) : ''}
      </button>
      {selectedTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label={t("SearchFilterBar_367")}>
          {selectedTags.map((tag) => (
            <button key={tag.id} type="button" onClick={() => onToggleTag(tag.id)} className="rounded-full bg-indigo-600 px-2.5 py-0.5 text-xs text-white">
              {tag.name} {t("SearchFilterBar_368")}</button>
          ))}
        </div>
      )}
      {open && (
        <div className="rounded border border-slate-200 bg-white p-2">
          <input
            autoFocus
            role="combobox"
            aria-label={t("SearchFilterBar_369")}
            aria-expanded="true"
            aria-controls={listboxId}
            aria-activedescendant={availableTags[activeIndex] ? `${listboxId}-${availableTags[activeIndex].id}` : undefined}
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActiveIndex(0) }}
            onCompositionStart={() => { composingRef.current = true }}
            onCompositionEnd={() => { composingRef.current = false }}
            onKeyDown={(event) => {
              if (isImeEvent(event.nativeEvent, composingRef.current)) return
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActiveIndex((index) => Math.min(index + 1, availableTags.length - 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActiveIndex((index) => Math.max(index - 1, 0))
              } else if (event.key === 'Enter' && availableTags[activeIndex]) {
                event.preventDefault()
                onToggleTag(availableTags[activeIndex].id)
              } else if (event.key === 'Escape') {
                event.preventDefault()
                setOpen(false)
              }
            }}
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <div id={listboxId} role="listbox" aria-label={t("SearchFilterBar_370")} aria-multiselectable="true" className="mt-1 max-h-48 overflow-y-auto">
            {availableTags.map((tag, index) => (
              <div
                id={`${listboxId}-${tag.id}`}
                key={tag.id}
                role="option"
                aria-selected={selectedTagIds.includes(tag.id)}
                data-active={index === activeIndex ? 'true' : undefined}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onToggleTag(tag.id)}
                className={`cursor-pointer rounded px-2 py-1 text-xs ${index === activeIndex ? 'bg-indigo-50 text-indigo-800' : 'text-slate-700'}`}
              >
                {tag.name}{selectedTagIds.includes(tag.id) ? ' ✓' : ''}
              </div>
            ))}
            {availableTags.length === 0 && <div className="px-2 py-1 text-xs text-slate-400">{t("SearchFilterBar_371")}</div>}
          </div>
        </div>
      )}
    </div>
  )
}
