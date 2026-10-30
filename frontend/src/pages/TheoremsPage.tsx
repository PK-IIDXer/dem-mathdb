import { useDisplayError } from "../i18n/useDisplayError"
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { EntityBadge } from '../components/BetaIdentity'
import { usePageTitle } from '../hooks/usePageTitle'
import { memo, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { FormulaPicker } from '../components/FormulaPicker'
import { SearchFilterBar } from '../components/SearchFilterBar'
import { ApiError } from '../api/client'
import type { Theorem } from '../api/types'
import { useReadOnly } from '../ReadOnlyContext'
import { symbolsApi } from '../api/symbols'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import { tagsApi } from '../api/tags'
import { OnboardingCoach } from '../components/OnboardingCoach'
import { ONBOARDING_TAG_NAME, onboardingQuery } from '../onboarding'
import { useCommand } from '../commands/CommandProvider'
import { hasPassedExternalCheck, theoremValidationCounts } from '../externalChecks'

export function TheoremsPage() {
  useLanguage()

  usePageTitle(t("ProofDetail_234"))
  const readOnly = useReadOnly()
  const formRef = useRef<HTMLFormElement>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const onboarding = searchParams.get('onboarding') === '1'
  const initialFormulaId = Number(searchParams.get('formula'))

  const [search, setSearch] = useState('')
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([])
  const toggleTag = (tagId: number) =>
    setSelectedTagIds((prev) => (prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]))

  const { data: theorems = [] } = useQuery({
    queryKey: ['theorems', { search, tagIds: selectedTagIds }],
    queryFn: () => theoremsApi.listVisible({ search: search || undefined, tagIds: selectedTagIds }),
  })
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const termVariables = useMemo(
    () => symbols.filter((symbol) => symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable),
    [symbols],
  )

  const [name, setName] = useState('')
  const [conclusionId, setConclusionId] = useState<number | null>(
    onboarding && Number.isInteger(initialFormulaId) && initialFormulaId > 0 ? initialFormulaId : null,
  )
  const [premiseIds, setPremiseIds] = useState<(number | null)[]>([])
  const [description, setDescription] = useState('')
  const [error, setError] = useDisplayError()
  const [variables, setVariables] = useState<{ name: string; symbolId: number }[]>([])
  const localContext = useMemo(
    () => Object.fromEntries(variables.filter((item) => item.name.trim()).map((item) => [item.name.trim(), item.symbolId])),
    [variables],
  )

  const registerMutation = useMutation({
    mutationFn: async () => {
      const onboardingTag = onboarding
        ? await tagsApi.getOrCreate(ONBOARDING_TAG_NAME)
        : null
      const theorem = await theoremsApi.register({
        name,
        conclusion_formula_id: conclusionId as number,
        premise_formula_ids: premiseIds as number[],
        tag_ids: onboardingTag ? [onboardingTag.id] : undefined,
        description: description.trim() || undefined,
        remarks: Object.keys(localContext).length > 0
          ? JSON.stringify({ phase1: { variables: localContext } })
          : undefined,
      })
      return theorem
    },
    onSuccess: (theorem) => {
      queryClient.invalidateQueries({ queryKey: ['theorems'] })
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      setName('')
      setConclusionId(null)
      setPremiseIds([])
      setDescription('')
      setVariables([])
      setError(null)
      navigate(`/theorems/${theorem.public_id}${onboarding ? onboardingQuery() : ''}`)
    },
    onError: (err) => setError(() => (err instanceof ApiError ? err.message : 'unknown error')),
  })

  const variableNames = variables.map((item) => item.name.trim())
  const variablesAreValid = variableNames.every(Boolean)
    && new Set(variableNames).size === variableNames.length
  const canSubmit = name && conclusionId != null && premiseIds.every((id) => id != null)
    && variablesAreValid && (!onboarding || variables.length === 1)
  const runCommit = useCommand('theorem.commit', () => registerMutation.mutate(), {
    enabled: Boolean(canSubmit) && !registerMutation.isPending,
    scope: formRef,
  })
  const runVariableAdd = useCommand('theorem.variable.add', () => {
    const used = new Set(variables.map((item) => item.symbolId))
    const available = termVariables.find((symbol) => !used.has(symbol.id))
    if (!available) return
    const candidateNames = ['x', 'y', 'z', 'a', 'b', 'c']
    const variableName = candidateNames.find((candidate) => !variables.some((item) => item.name === candidate)) ?? `x${variables.length + 1}`
    setVariables((items) => [...items, { name: variableName, symbolId: available.id }])
  }, { enabled: termVariables.length > variables.length, scope: formRef })
  const runPremiseAdd = useCommand('theorem.premise.add', () => setPremiseIds((prev) => [...prev, null]), { scope: formRef })

  function movePremise(index: number, direction: -1 | 1) {
    setPremiseIds((prev) => {
      const next = [...prev]
      const target = index + direction
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  return (
    <div className="space-y-6">
      {!readOnly && (
      <section className={`rounded-lg border border-slate-200 p-4 ${onboarding ? 'ring-4 ring-indigo-200' : ''}`}>
        <h2 className="mb-3 text-sm font-semibold text-slate-700">{t("TheoremsPage_810")}</h2>
        <form
          ref={formRef}
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            runCommit()
          }}
        >
          <label className="flex flex-col text-xs text-slate-500">
            name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>

          <div className="rounded border border-slate-200 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">{t("TheoremsPage_811")}</span>
              <button
                type="button"
                onClick={() => runVariableAdd()}
                className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200"
              >
                {t("TheoremsPage_812")}</button>
            </div>
            <div className="space-y-2">
              {variables.map((variable, index) => (
                <div key={variable.symbolId} className="grid grid-cols-[1fr_auto_auto] items-center gap-2">
                  <input
                    value={variable.name}
                    onChange={(event) => setVariables((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))}
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                    aria-label={t("TheoremsPage_813", index + 1)}
                  />
                  <span className="text-xs text-slate-500">{t("TheoremsPage_814")}</span>
                  <button
                    type="button"
                    onClick={() => setVariables((items) => items.filter((_, itemIndex) => itemIndex !== index))}
                    className="px-1 text-xs text-red-600"
                  >
                    ×
                  </button>
                </div>
              ))}
              {variables.length === 0 && <p className="text-xs text-slate-400">{t("TheoremsPage_815")}</p>}
              {!variablesAreValid && (
                <p className="text-xs text-red-600">{t("TheoremsPage_816")}</p>
              )}
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs text-slate-500">conclusion</div>
            <FormulaPicker value={conclusionId} onChange={setConclusionId} context={localContext} />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
              <span>{t("TheoremsPage_817")}</span>
              <button
                type="button"
                onClick={() => runPremiseAdd()}
                className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
              >
                {t("SubstitutionEditor_424")}</button>
            </div>
            <div className="space-y-2">
              {premiseIds.map((premiseId, index) => (
                <div key={index} className="flex items-start gap-2">
                  <span className="mt-2 w-6 text-xs text-slate-400">#{index}</span>
                  <div className="flex-1">
                    <FormulaPicker
                      value={premiseId}
                      context={localContext}
                      onChange={(id) =>
                        setPremiseIds((prev) => prev.map((p, i) => (i === index ? id : p)))
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => movePremise(index, -1)}
                      disabled={index === 0}
                      className="rounded bg-slate-100 px-1 text-xs disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => movePremise(index, 1)}
                      disabled={index === premiseIds.length - 1}
                      className="rounded bg-slate-100 px-1 text-xs disabled:opacity-30"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => setPremiseIds((prev) => prev.filter((_, i) => i !== index))}
                      className="rounded bg-slate-100 px-1 text-xs text-red-600"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
              {premiseIds.length === 0 && <p className="text-xs text-slate-400">{t("ExplorationsPage_628")}</p>}
            </div>
          </div>

          <label className="flex flex-col text-xs text-slate-500">
            {t("AxiomsPage_482")}<textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder={t("TheoremsPage_821")}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>

          <button
            type="submit"
            disabled={!canSubmit || registerMutation.isPending}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {t("TheoremsPage_822")}<kbd aria-hidden="true" className="ml-1 text-xs">Ctrl/⌘ Enter</kbd>
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      </section>
      )}

      {onboarding && (
        <OnboardingCoach step={2} title={t("TheoremsPage_823")}>
          <p>{t("TheoremsPage_824")}<code>my_first_theorem</code> {t("TheoremsPage_825")}</p>
          <p>{t("TheoremsPage_826")}<code>{t("TheoremsPage_827")}</code> {t("TheoremsPage_828")}</p>
          <p>{t("TheoremsPage_829")}</p>
        </OnboardingCoach>
      )}

      <SearchFilterBar
        search={search}
        onSearchChange={setSearch}
        selectedTagIds={selectedTagIds}
        onToggleTag={toggleTag}
      />

      <TheoremTable theorems={theorems} />
    </div>
  )
}

/** Memoized so a keystroke in the registration form, which re-renders the
 * page, leaves the theorem rows alone until the list itself changes. */
const TheoremTable = memo(function TheoremTable({ theorems }: { theorems: Theorem[] }) {
  useLanguage()

  const validationCounts = theoremValidationCounts(theorems)
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-slate-700">{t("TheoremsPage_830")}{theorems.length})</h2>
      <p className="mb-2 text-xs text-slate-500">
        {t("TheoremsPage_831")}{validationCounts.demProven} {t("TheoremSearchPage_805")}{validationCounts.leanOnly}
      </p>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500">
          <tr>
            <th className="py-1 pr-3">{t("AxiomsPage_486")}</th>
            <th className="py-1 pr-3">status</th>
          </tr>
        </thead>
        <tbody>
          {theorems.map((theorem) => (
            <tr
              key={theorem.id}
              className="border-t border-slate-100 hover:bg-slate-50"
            >
              <td className="py-1 pr-3">
                <Link
                  to={`/theorems/${theorem.public_id}`}
                  className="font-mono text-indigo-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                >
                  {theorem.name}
                </Link> <EntityBadge namespace={theorem.namespace_name} />
                {theorem.description && (
                  <div className="text-xs text-slate-500">{theorem.description}</div>
                )}
                {theorem.tags.length > 0 && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
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
              </td>
              <td className="py-1 pr-3 align-top text-slate-500">
                <div>DEM: {theorem.status === 'proven' ? t("DependencyGraph_126") : t("DependencyGraph_125")}</div>
                {hasPassedExternalCheck(theorem) && (
                  <div className="text-indigo-700">{t("TheoremSearchPage_806")}</div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
})
