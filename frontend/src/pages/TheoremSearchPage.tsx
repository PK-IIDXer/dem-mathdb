import { memo, useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams, type NavigateFunction } from 'react-router-dom'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { tagsApi } from '../api/tags'
import { theoremsApi } from '../api/theorems'
import type { Theorem } from '../api/types'
import { FormulaPreview } from '../components/FormulaPreview'
import { SearchFilterBar } from '../components/SearchFilterBar'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { usePrimeFormulas } from '../hooks/useFormulaLatex'

/** How long the search box must stay unchanged before a theorem request is sent. */
export const SEARCH_DEBOUNCE_MS = 300

const NO_THEOREMS: Theorem[] = []

function parseTagIds(value: string | null): number[] {
  if (!value) return []
  return value
    .split(',')
    .map(Number)
    .filter((id) => !Number.isNaN(id))
}

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'すべて' },
  { value: 'conjecture', label: '未証明' },
  { value: 'proven', label: '証明済み' },
]

const STATUS_BADGE: Record<string, string> = {
  conjecture: 'bg-slate-200 text-slate-700',
  proven: 'bg-green-100 text-green-800',
}

const STATUS_LABEL: Record<string, string> = {
  conjecture: '未証明',
  proven: '証明済み',
}

export function TheoremSearchPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState(() => searchParams.get('q') ?? '')
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>(() => parseTagIds(searchParams.get('tags')))
  const [status, setStatus] = useState(() => searchParams.get('status') ?? '')
  const toggleTag = useCallback(
    (tagId: number) =>
      setSelectedTagIds((prev) => (prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId])),
    [],
  )
  // The input follows every keystroke; the URL and the request follow the
  // search only once typing pauses.
  const debouncedSearch = useDebouncedValue(search, SEARCH_DEBOUNCE_MS)

  useEffect(() => {
    const next = new URLSearchParams()
    if (debouncedSearch) next.set('q', debouncedSearch)
    if (selectedTagIds.length > 0) next.set('tags', selectedTagIds.join(','))
    if (status) next.set('status', status)
    setSearchParams(next, { replace: true })
  }, [debouncedSearch, selectedTagIds, status, setSearchParams])

  const { data: theorems = NO_THEOREMS } = useQuery({
    queryKey: ['theorems', { search: debouncedSearch, tagIds: selectedTagIds, status }],
    queryFn: () =>
      theoremsApi.listVisible(
        { search: debouncedSearch || undefined, tagIds: selectedTagIds, status: status || undefined },
        // Shares SearchFilterBar's ['tags'] query instead of refetching /tags per
        // search, but refetches once it has been invalidated (e.g. the onboarding
        // tag was just created), so the exclusion is not built from a stale list.
        () => queryClient.fetchQuery({ queryKey: ['tags'], queryFn: () => tagsApi.list(), staleTime: 5 * 60_000 }),
      ),
    // Keep the current cards on screen while the next result loads, rather than
    // unmounting them and showing "no results" in between.
    placeholderData: keepPreviousData,
  })

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">定理を探す</h2>

      <SearchFilterBar
        search={search}
        onSearchChange={setSearch}
        selectedTagIds={selectedTagIds}
        onToggleTag={toggleTag}
        placeholder="検索 (name / 説明)"
      />

      <div className="flex gap-2">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatus(opt.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              status === opt.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <TheoremResults theorems={theorems} navigate={navigate} />
    </div>
  )
}

/** Memoized so a keystroke, which re-renders the page, leaves the cards alone
 * until the result list itself changes. `navigate` is passed in rather than
 * read here: useNavigate subscribes to the location, which changes whenever the
 * page rewrites the query string. */
const TheoremResults = memo(function TheoremResults({
  theorems,
  navigate,
}: {
  theorems: Theorem[]
  navigate: NavigateFunction
}) {
  // One request for the conclusions not cached yet, instead of one FormulaPreview
  // fetch per card. Called here rather than in the page so the memo still holds.
  const formulasWaiting = usePrimeFormulas(theorems.map((theorem) => theorem.conclusion_formula_id))
  return (
    <>
      <div className="text-xs text-slate-500">{theorems.length} 件</div>

      <div className="grid grid-cols-2 gap-3">
        {theorems.map((theorem) => (
          <button
            key={theorem.id}
            type="button"
            onClick={() => navigate(`/theorems/${theorem.public_id}`)}
            className="rounded-lg border border-slate-200 p-4 text-left hover:border-indigo-300 hover:bg-indigo-50/40"
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="font-mono text-sm text-slate-800">{theorem.name}</span>
              <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${STATUS_BADGE[theorem.status]}`}>
                {STATUS_LABEL[theorem.status] ?? theorem.status}
              </span>
            </div>
            <div className="mb-2 text-sm">
              {/* Only cards whose formula is in the pending batch wait; cached ones
                  stay on screen while the next result's formulas load. */}
              {formulasWaiting.has(theorem.conclusion_formula_id) ? (
                <span className="text-slate-400">読み込み中…</span>
              ) : (
                <FormulaPreview formulaId={theorem.conclusion_formula_id} />
              )}
            </div>
            {theorem.description && (
              <p className="mb-2 text-xs text-slate-500">{theorem.description}</p>
            )}
            {theorem.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {theorem.tags.map((tag) => (
                  <span
                    key={tag.id}
                    className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700"
                  >
                    {tag.name}
                  </span>
                ))}
              </div>
            )}
          </button>
        ))}
        {theorems.length === 0 && (
          <p className="col-span-2 text-sm text-slate-400">条件に一致する定理がありません</p>
        )}
      </div>
    </>
  )
})
