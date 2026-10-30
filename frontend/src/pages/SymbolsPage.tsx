import { useDisplayError } from "../i18n/useDisplayError"
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { EntityBadge } from '../components/BetaIdentity'
import { usePageTitle } from '../hooks/usePageTitle'
import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { symbolsApi } from '../api/symbols'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'
import type { NotationKind } from '../api/types'
import { Latex } from '../components/Latex'
import { ambiguousSymbolGroups, renderTemplateSample } from '../components/FormulaEditor/model'

export function SymbolsPage() {
  useLanguage()

  usePageTitle(t("SymbolDetailPage_714"))
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const { data: symbolTypes = [] } = useQuery({
    queryKey: ['symbolTypes'],
    queryFn: () => symbolsApi.listSymbolTypes(),
  })
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })

  const [name, setName] = useState('')
  const [symbolTypeId, setSymbolTypeId] = useState<number | ''>('')
  const [arity, setArity] = useState(0)
  const [isPrimitive, setIsPrimitive] = useState(false)
  const [notationKind, setNotationKind] = useState<NotationKind>('prefix')
  const [precedence, setPrecedence] = useState<number | ''>('')
  const [latexTemplate, setLatexTemplate] = useState('')
  const [error, setError] = useDisplayError()
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editNotationKind, setEditNotationKind] = useState<NotationKind>('prefix')
  const [editPrecedence, setEditPrecedence] = useState<number | ''>('')
  const [editLatexTemplate, setEditLatexTemplate] = useState('')
  const [search, setSearch] = useState('')
  const [filterTypeId, setFilterTypeId] = useState<number | ''>('')

  const filteredSymbols = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase()

    return symbols.filter((symbol) => {
      if (filterTypeId !== '' && symbol.symbol_type_id !== filterTypeId) return false
      if (!normalizedSearch) return true

      return [symbol.name, symbol.namespace_name, symbol.remarks, symbol.latex_template]
        .filter((value): value is string => value != null)
        .some((value) => value.toLocaleLowerCase().includes(normalizedSearch))
    })
  }, [filterTypeId, search, symbols])

  const hasSearchFilters = search.trim() !== '' || filterTypeId !== ''
  const ambiguousGroups = useMemo(() => ambiguousSymbolGroups(symbols), [symbols])

  const registerMutation = useMutation({
    mutationFn: () =>
      symbolsApi.register({
        name,
        symbol_type_id: Number(symbolTypeId),
        arity,
        is_primitive: isPrimitive,
        notation_kind: notationKind,
        precedence: notationKind === 'infix' ? Number(precedence) : null,
        latex_template: latexTemplate || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['symbols'] })
      setName('')
      setArity(0)
      setIsPrimitive(false)
      setNotationKind('prefix')
      setPrecedence('')
      setLatexTemplate('')
      setError(null)
    },
    onError: (err) => setError(() => (err instanceof ApiError ? err.message : 'unknown error')),
  })

  const notationMutation = useMutation({
    mutationFn: (symbolId: number) =>
      symbolsApi.setNotation(
        symbolId,
        editNotationKind,
        editNotationKind === 'infix' ? Number(editPrecedence) : null,
      ),
  })

  const latexTemplateMutation = useMutation({
    mutationFn: (symbolId: number) => symbolsApi.setLatexTemplate(symbolId, editLatexTemplate || null),
  })

  const saveDisplaySettings = useMutation({
    mutationFn: async (symbolId: number) => {
      await Promise.all([notationMutation.mutateAsync(symbolId), latexTemplateMutation.mutateAsync(symbolId)])
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['symbols'] })
      setEditingId(null)
    },
    onError: (err) => setError(() => (err instanceof ApiError ? err.message : 'unknown error')),
  })

  const selectedType = symbolTypes.find((t) => t.id === symbolTypeId)
  const arityLocked = selectedType?.fixed_arity != null
  const canRegisterInfix = arity === 2
  const canSubmit =
    name &&
    symbolTypeId !== '' &&
    (notationKind === 'prefix' || (canRegisterInfix && precedence !== ''))

  function startEditing(
    symbolId: number,
    current: NotationKind,
    currentPrecedence: number | null,
    currentLatexTemplate: string | null,
  ) {
    setEditingId(symbolId)
    setEditNotationKind(current)
    setEditPrecedence(currentPrecedence ?? '')
    setEditLatexTemplate(currentLatexTemplate ?? '')
    setError(null)
  }

  return (
    <div className="space-y-6">
      {!readOnly && (
      <section className="rounded-lg border border-slate-200 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">{t("SymbolsPage_720")}</h2>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            registerMutation.mutate()
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
          <label className="flex flex-col text-xs text-slate-500">
            symbol_type
            <select
              value={symbolTypeId}
              onChange={(e) => {
                const id = Number(e.target.value)
                setSymbolTypeId(id)
                const type = symbolTypes.find((t) => t.id === id)
                if (type?.fixed_arity != null) setArity(type.fixed_arity)
              }}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="" disabled>
                {t("StepForm_381")}</option>
              {symbolTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-xs text-slate-500">
            arity
            <input
              type="number"
              min={0}
              value={arity}
              disabled={arityLocked}
              onChange={(e) => {
                const value = Number(e.target.value)
                setArity(value)
                if (value !== 2) setNotationKind('prefix')
              }}
              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
            />
          </label>
          <label className="flex items-center gap-1 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={isPrimitive}
              onChange={(e) => setIsPrimitive(e.target.checked)}
            />
            is_primitive
          </label>
          <label className="flex flex-col text-xs text-slate-500">
            {t("SymbolsPage_722")}<select
              value={notationKind}
              onChange={(e) => setNotationKind(e.target.value as NotationKind)}
              disabled={!canRegisterInfix}
              className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
            >
              <option value="prefix">{t("SymbolsPage_723")}</option>
              <option value="infix">{t("SymbolsPage_724")}</option>
            </select>
          </label>
          {notationKind === 'infix' && (
            <label className="flex flex-col text-xs text-slate-500">
              {t("SymbolsPage_725")}<input
                type="number"
                value={precedence}
                onChange={(e) => setPrecedence(e.target.value === '' ? '' : Number(e.target.value))}
                className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>
          )}
          <label className="flex flex-col text-xs text-slate-500">
            {t("SymbolsPage_726")}<input
              value={latexTemplate}
              onChange={(e) => setLatexTemplate(e.target.value)}
              placeholder={t("SymbolsPage_727")}
              className="w-40 rounded border border-slate-300 px-2 py-1 text-sm font-mono"
            />
          </label>
          {latexTemplate && (
            <div className="rounded border border-slate-100 bg-white px-2 py-1">
              <Latex>{renderTemplateSample(latexTemplate, selectedType?.is_quantifier ?? false)}</Latex>
            </div>
          )}
          <button
            type="submit"
            disabled={!canSubmit || registerMutation.isPending}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {t("AxiomsPage_484")}</button>
        </form>
        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      </section>
      )}

      <section className="space-y-3">
        <details className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-amber-900">
            {t("SymbolsPage_729")}{ambiguousGroups.length} {t("SymbolsPage_730")}</summary>
          {ambiguousGroups.length === 0 ? (
            <p className="mt-2 text-xs text-amber-800">{t("SymbolsPage_731")}</p>
          ) : (
            <ul className="mt-2 space-y-2 text-xs text-amber-950">
              {ambiguousGroups.map((group) => (
                <li key={`${group.kind}:${group.spelling}`}>
                  <span className="font-medium">
                    {group.kind === 'name' ? t("SymbolsPage_732") : t("SymbolsPage_733")}「{group.spelling}」
                  </span>
                  <span className="ml-2 font-mono">
                    {group.symbols.map((symbol) => `${symbol.namespace_name}::${symbol.name}`).join(' / ')}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </details>
        <div className="rounded-lg border border-slate-200 p-3">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">{t("FormulaEditor_167")}</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-64 flex-1 text-xs text-slate-500">
              {t("SymbolsPage_735")}<input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="name / remarks / LaTeX"
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
              />
            </label>
            <label className="flex min-w-56 flex-col text-xs text-slate-500">
              type
              <select
                value={filterTypeId}
                onChange={(e) => setFilterTypeId(e.target.value === '' ? '' : Number(e.target.value))}
                className="mt-1 rounded border border-slate-300 px-2 py-1 text-sm"
              >
                <option value="">{t("SymbolsPage_736")}</option>
                {symbolTypes.map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={!hasSearchFilters}
              onClick={() => {
                setSearch('')
                setFilterTypeId('')
              }}
              className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40"
            >
              {t("SymbolsPage_737")}</button>
          </div>
        </div>

        <h2 className="text-sm font-semibold text-slate-700">
          {t("SymbolsPage_738")}{filteredSymbols.length}{hasSearchFilters ? ` / ${symbols.length}` : ''})
        </h2>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3">name</th>
              <th className="py-1 pr-3">type</th>
              <th className="py-1 pr-3">arity</th>
              <th className="py-1 pr-3">primitive</th>
              <th className="py-1 pr-3">{t("SymbolsPage_722")}</th>
              <th className="py-1 pr-3">{t("SymbolsPage_725")}</th>
              <th className="py-1 pr-3">LaTeX</th>
              <th className="py-1 pr-3">remarks</th>
              <th className="py-1 pr-3"></th>
            </tr>
          </thead>
          <tbody>
            {filteredSymbols.map((symbol) => (
              <Fragment key={symbol.id}>
                <tr className="border-t border-slate-100">
                  <td className="py-1 pr-3 font-mono">
                    <Link to={`/symbols/${symbol.public_id}`} className="text-indigo-600 hover:underline">
                      {symbol.name}
                    </Link> <EntityBadge namespace={symbol.namespace_name} />
                  </td>
                  <td className="py-1 pr-3">{symbol.symbol_type.name}</td>
                  <td className="py-1 pr-3">{symbol.arity}</td>
                  <td className="py-1 pr-3">{symbol.is_primitive ? '✓' : ''}</td>
                  <td className="py-1 pr-3">{symbol.notation_kind}</td>
                  <td className="py-1 pr-3">{symbol.precedence ?? ''}</td>
                  <td className="py-1 pr-3">
                    {symbol.latex_template && (
                      <Latex>{renderTemplateSample(symbol.latex_template, symbol.symbol_type.is_quantifier)}</Latex>
                    )}
                  </td>
                  <td className="py-1 pr-3 text-slate-500">{symbol.remarks}</td>
                  <td className="py-1 pr-3">
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() =>
                          startEditing(symbol.id, symbol.notation_kind, symbol.precedence, symbol.latex_template)
                        }
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        {t("SymbolsPage_741")}</button>
                    )}
                  </td>
                </tr>
                {!readOnly && editingId === symbol.id && (
                  <tr className="bg-slate-50">
                    <td colSpan={9} className="px-3 py-2">
                      <div className="flex flex-wrap items-end gap-3">
                        <label className="flex flex-col text-xs text-slate-500">
                          {t("SymbolsPage_722")}<select
                            value={editNotationKind}
                            onChange={(e) => setEditNotationKind(e.target.value as NotationKind)}
                            disabled={symbol.arity !== 2}
                            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
                          >
                            <option value="prefix">{t("SymbolsPage_723")}</option>
                            <option value="infix">{t("SymbolsPage_744")}</option>
                          </select>
                        </label>
                        {editNotationKind === 'infix' && (
                          <label className="flex flex-col text-xs text-slate-500">
                            {t("SymbolsPage_725")}<input
                              type="number"
                              value={editPrecedence}
                              onChange={(e) =>
                                setEditPrecedence(e.target.value === '' ? '' : Number(e.target.value))
                              }
                              className="w-20 rounded border border-slate-300 px-2 py-1 text-sm"
                            />
                          </label>
                        )}
                        <label className="flex flex-col text-xs text-slate-500">
                          {t("SymbolsPage_746")}<input
                            value={editLatexTemplate}
                            onChange={(e) => setEditLatexTemplate(e.target.value)}
                            placeholder={t("SymbolsPage_727")}
                            className="w-40 rounded border border-slate-300 px-2 py-1 text-sm font-mono"
                          />
                        </label>
                        {editLatexTemplate && (
                          <div className="rounded border border-slate-100 bg-white px-2 py-1">
                            <Latex>{renderTemplateSample(editLatexTemplate, symbol.symbol_type.is_quantifier)}</Latex>
                          </div>
                        )}
                        <button
                          type="button"
                          disabled={
                            (editNotationKind === 'infix' && editPrecedence === '') ||
                            saveDisplaySettings.isPending
                          }
                          onClick={() => saveDisplaySettings.mutate(symbol.id)}
                          className="rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-40"
                        >
                          {t("DescriptionEditor_138")}</button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="text-xs text-slate-500 hover:underline"
                        >
                          {t("SymbolsPage_749")}</button>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {filteredSymbols.length === 0 && (
              <tr>
                <td colSpan={9} className="border-t border-slate-100 py-8 text-center text-sm text-slate-400">
                  {t("SymbolsPage_750")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  )
}
