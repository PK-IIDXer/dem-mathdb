import { useDisplayError } from "../i18n/useDisplayError"
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { EntityBadge } from '../components/BetaIdentity'
import { usePageTitle } from '../hooks/usePageTitle'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { definitionsApi } from '../api/definitions'
import { formulasApi } from '../api/formulas'
import { symbolsApi } from '../api/symbols'
import { FormulaPicker } from '../components/FormulaPicker'
import { Latex } from '../components/Latex'
import { renderTemplateSample } from '../components/FormulaEditor/model'
import {
  definitionTemplateChoices,
  type DefinitionTemplateMode,
} from '../components/DefinitionTemplate/definitionTemplate'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import { SearchFilterBar } from '../components/SearchFilterBar'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'
import type { DefinitionCreateKind } from '../api/types'
import {
  DEFINITION_CREATE_KINDS,
  inferDefinitionKind,
} from '../components/DefinitionKind/definitionKindInference'

const KIND_LABEL: Record<DefinitionCreateKind, string> = {
  get predicate() { return t("DefinitionsPage_565") },
  get function() { return t("DefinitionsPage_566") },
  get logical() { return t("DefinitionsPage_567") },
  get quant_prop() { return t("DefinitionsPage_568") },
  get quant_term() { return t("DefinitionsPage_569") },
}

const BODY_TYPE_HINT: Record<DefinitionCreateKind, string> = {
  get predicate() { return t("DefinitionsPage_570") },
  get function() { return t("DefinitionsPage_571") },
  get logical() { return t("DefinitionsPage_570") },
  get quant_prop() { return t("DefinitionsPage_570") },
  get quant_term() { return t("DefinitionsPage_571") },
}

const SINGLE_PARAM_KINDS: DefinitionCreateKind[] = ['logical', 'quant_prop', 'quant_term']

export function DefinitionsPage() {
  useLanguage()

  usePageTitle(t("DefinitionDetailPage_560"))
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([])
  const toggleTag = (tagId: number) =>
    setSelectedTagIds((prev) => (prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]))

  const { data: definitions = [] } = useQuery({
    queryKey: ['definitions', { search, tagIds: selectedTagIds }],
    queryFn: () => definitionsApi.list({ search: search || undefined, tagIds: selectedTagIds }),
  })
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols() })

  const [manualKind, setManualKind] = useState<DefinitionCreateKind | null>(null)
  const [name, setName] = useState('')
  const [paramIds, setParamIds] = useState<number[]>([])
  const [bodyId, setBodyId] = useState<number | null>(null)
  const [requiresExistence, setRequiresExistence] = useState(false)
  const [requiresUniqueness, setRequiresUniqueness] = useState(false)
  const [templateMode, setTemplateMode] = useState<DefinitionTemplateMode | null>(null)
  const [customLatexTemplate, setCustomLatexTemplate] = useState('')
  const [error, setError] = useDisplayError()

  const { data: bodyFormula } = useQuery({
    queryKey: ['formulas', bodyId],
    queryFn: () => formulasApi.get(bodyId as number),
    enabled: bodyId != null,
  })
  const paramCandidates = symbols.filter((symbol) =>
    symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable
      || (symbol.symbol_type.name === SYMBOL_TYPE.freePropositionVariable
        && (symbol.arity === 0 || symbol.arity === 1)),
  )
  const paramShapes = useMemo(() => paramIds.map((id) => {
    const symbol = symbols.find((candidate) => candidate.id === id)
    return symbol ? { symbolTypeName: symbol.symbol_type.name, arity: symbol.arity } : null
  }), [paramIds, symbols])
  const inferredKind = paramShapes.every((shape) => shape != null)
    ? inferDefinitionKind(
        paramShapes,
        bodyFormula?.formula_type.code ?? null,
      )
    : null
  const kind = manualKind ?? inferredKind ?? 'logical'

  const isSingleParam = SINGLE_PARAM_KINDS.includes(kind)
  const showExistenceUniqueness = kind === 'predicate'
  const activeTemplateMode = templateMode ?? (kind === 'predicate' ? 'is-has' : 'as-is')
  const templateChoices = definitionTemplateChoices(name)
  const selectedLatexTemplate = activeTemplateMode === 'as-is'
    ? templateChoices.asIs
    : activeTemplateMode === 'is-has'
      ? templateChoices.isHas
      : customLatexTemplate
  const isQuantifier = kind === 'quant_prop' || kind === 'quant_term'
  const customTemplateIsValid = customLatexTemplate.trim().length > 0
    && customLatexTemplate.length <= 1000

  const registerMutation = useMutation({
    mutationFn: () =>
      definitionsApi.register({
        kind,
        name,
        param_symbol_ids: paramIds,
        body_formula_id: bodyId as number,
        requires_existence_proof: showExistenceUniqueness ? requiresExistence : undefined,
        requires_uniqueness_proof: showExistenceUniqueness ? requiresUniqueness : undefined,
        latex_template: selectedLatexTemplate,
      }),
    onSuccess: (definition) => {
      queryClient.invalidateQueries({ queryKey: ['definitions'] })
      queryClient.invalidateQueries({ queryKey: ['symbols'] })
      setName('')
      setParamIds([])
      setBodyId(null)
      setManualKind(null)
      setRequiresExistence(false)
      setRequiresUniqueness(false)
      setTemplateMode(null)
      setCustomLatexTemplate('')
      setError(null)
      navigate(`/definitions/${definition.public_id}`)
    },
    onError: (err) => setError(() => (err instanceof ApiError ? err.message : 'unknown error')),
  })

  const canSubmit =
    name.trim() !== '' &&
    bodyId != null &&
    (isSingleParam ? paramIds.length === 1 : true) &&
    (activeTemplateMode !== 'custom' || customTemplateIsValid)

  return (
    <div className="space-y-6">
      {!readOnly && (
      <section className="rounded-lg border border-slate-200 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">{t("DefinitionsPage_576")}</h2>

        <div className="mb-2 text-xs text-slate-600" role="status">
          {t("DefinitionsPage_577")}{' '}
          <strong>{inferredKind ? KIND_LABEL[inferredKind] : t("DefinitionsPage_578")}</strong>
          {manualKind && (
            <>
              <span className="ml-2">{t("DefinitionsPage_579")}{KIND_LABEL[manualKind]}{t("DefinitionsPage_580")}</span>
              <button
                type="button"
                onClick={() => setManualKind(null)}
                className="ml-2 text-indigo-700 underline"
              >
                {t("DefinitionsPage_581")}</button>
            </>
          )}
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          {DEFINITION_CREATE_KINDS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setManualKind(k)}
              aria-pressed={kind === k}
              className={`rounded px-2 py-1 text-xs ${
                kind === k ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <label className="block text-xs text-slate-500">
            {t("DefinitionsPage_582")}<input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>

          <fieldset className="space-y-2 rounded border border-slate-200 p-3">
            <legend className="px-1 text-xs font-medium text-slate-600">{t("DefinitionsPage_583")}</legend>

            <label className="grid cursor-pointer grid-cols-[auto_7rem_1fr] items-center gap-2 rounded p-2 hover:bg-slate-50">
              <input
                aria-label={t("DefinitionsPage_584")}
                type="radio"
                name="definition-template"
                checked={activeTemplateMode === 'as-is'}
                onClick={() => setTemplateMode('as-is')}
                onChange={() => setTemplateMode('as-is')}
              />
              <span className="text-xs text-slate-600">{t("DefinitionsPage_584")}</span>
              <span data-testid="definition-template-preview" className="min-w-0 overflow-x-auto rounded bg-slate-50 px-2 py-1">
                <Latex>{renderTemplateSample(templateChoices.asIs, isQuantifier)}</Latex>
              </span>
            </label>

            <label className="grid cursor-pointer grid-cols-[auto_7rem_1fr] items-center gap-2 rounded p-2 hover:bg-slate-50">
              <input
                aria-label={t("DefinitionsPage_586", templateChoices.isHasPrefix)}
                type="radio"
                name="definition-template"
                checked={activeTemplateMode === 'is-has'}
                onClick={() => setTemplateMode('is-has')}
                onChange={() => setTemplateMode('is-has')}
              />
              <span className="text-xs text-slate-600">{templateChoices.isHasPrefix} {t("DefinitionsPage_587")}</span>
              <span data-testid="definition-template-preview" className="min-w-0 overflow-x-auto rounded bg-slate-50 px-2 py-1">
                <Latex>{renderTemplateSample(templateChoices.isHas, isQuantifier)}</Latex>
              </span>
            </label>

            <div className="grid grid-cols-[auto_7rem_1fr] items-start gap-2 rounded p-2 hover:bg-slate-50">
              <input
                aria-label={t("DefinitionsPage_588")}
                type="radio"
                name="definition-template"
                checked={activeTemplateMode === 'custom'}
                onClick={() => setTemplateMode('custom')}
                onChange={() => setTemplateMode('custom')}
              />
              <label htmlFor="definition-custom-template" className="cursor-pointer text-xs text-slate-600">{t("DefinitionsPage_588")}</label>
              <div className="space-y-1">
                <input
                  id="definition-custom-template"
                  aria-label={t("DefinitionsPage_590")}
                  value={customLatexTemplate}
                  maxLength={1000}
                  placeholder="#2 \\circ_{#1} #3"
                  onFocus={() => setTemplateMode('custom')}
                  onChange={(event) => {
                    setTemplateMode('custom')
                    setCustomLatexTemplate(event.target.value)
                  }}
                  className="w-full rounded border border-slate-300 px-2 py-1 font-mono text-xs"
                />
                <div data-testid="definition-template-preview" className="min-h-7 overflow-x-auto rounded bg-slate-50 px-2 py-1">
                  <Latex>{renderTemplateSample(customLatexTemplate.trim() || templateChoices.asIs, isQuantifier)}</Latex>
                </div>
                <p className="text-[10px] text-slate-500">{t("DefinitionsPage_591")}</p>
              </div>
            </div>
          </fieldset>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
              <span>{t("DefinitionsPage_592")}</span>
              <button
                type="button"
                disabled={paramCandidates.length === 0}
                onClick={() => setParamIds([...paramIds, paramCandidates[0]?.id ?? 0])}
                className="rounded bg-slate-100 px-2 py-0.5 text-xs hover:bg-slate-200 disabled:opacity-40"
              >
                {t("SubstitutionEditor_424")}</button>
            </div>

            <div className="space-y-1">
              {paramIds.map((paramId, index) => (
                <div key={index} className="flex items-center gap-1">
                  <select
                    aria-label={`formal param ${index + 1}`}
                    value={paramId}
                    onChange={(e) => {
                      const next = [...paramIds]
                      next[index] = Number(e.target.value)
                      setParamIds(next)
                    }}
                    className="rounded border border-slate-300 px-2 py-1 text-xs"
                  >
                    {paramCandidates.map((sym) => (
                      <option key={sym.id} value={sym.id}>
                        {sym.name} ({sym.symbol_type.name}, arity {sym.arity})
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label={t("DefinitionsPage_594", index + 1)}
                    disabled={index === 0}
                    onClick={() => {
                      const next = [...paramIds]
                      ;[next[index - 1], next[index]] = [next[index], next[index - 1]]
                      setParamIds(next)
                    }}
                    className="rounded bg-slate-100 px-1 text-xs disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={t("DefinitionsPage_595", index + 1)}
                    disabled={index === paramIds.length - 1}
                    onClick={() => {
                      const next = [...paramIds]
                      ;[next[index], next[index + 1]] = [next[index + 1], next[index]]
                      setParamIds(next)
                    }}
                    className="rounded bg-slate-100 px-1 text-xs disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={t("DefinitionsPage_596", index + 1)}
                    onClick={() => setParamIds(paramIds.filter((_, i) => i !== index))}
                    className="text-slate-400 hover:text-red-600"
                  >
                    ×
                  </button>
                </div>
              ))}
              {paramIds.length === 0 && <p className="text-xs text-slate-400">{t("DefinitionsPage_597")}</p>}
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs text-slate-500">{t("DefinitionsPage_598")}{BODY_TYPE_HINT[kind]})</div>
            <FormulaPicker value={bodyId} onChange={setBodyId} />
          </div>

          {showExistenceUniqueness && (
            <div className="flex gap-4 text-xs text-slate-500">
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={requiresExistence}
                  onChange={(e) => setRequiresExistence(e.target.checked)}
                />
                requires_existence_proof
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={requiresUniqueness}
                  onChange={(e) => setRequiresUniqueness(e.target.checked)}
                />
                requires_uniqueness_proof
              </label>
            </div>
          )}

          <button
            type="button"
            disabled={!canSubmit || registerMutation.isPending}
            onClick={() => registerMutation.mutate()}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {t("AxiomsPage_484")}</button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </div>
      </section>
      )}

      <SearchFilterBar
        search={search}
        onSearchChange={setSearch}
        selectedTagIds={selectedTagIds}
        onToggleTag={toggleTag}
      />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-slate-700">
          {t("DefinitionsPage_600")}{definitions.length})
        </h2>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3">{t("AxiomsPage_486")}</th>
              <th className="py-1 pr-3">kind</th>
            </tr>
          </thead>
          <tbody>
            {definitions.map((definition) => (
              <tr
                key={definition.id}
                className="border-t border-slate-100 hover:bg-slate-50"
              >
                <td className="py-1 pr-3">
                  <Link
                    to={`/definitions/${definition.public_id}`}
                    className="font-mono text-indigo-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                  >
                    {definition.name}
                  </Link> <EntityBadge namespace={definition.namespace_name} />
                  {definition.description && (
                    <div className="text-xs text-slate-500">{definition.description}</div>
                  )}
                  {definition.tags.length > 0 && (
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {definition.tags.map((tag) => (
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
                <td className="py-1 pr-3 align-top text-slate-500">{definition.kind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
