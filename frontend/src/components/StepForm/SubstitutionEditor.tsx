import { useLayoutEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { formulasApi } from '../../api/formulas'
import type { PropSubst, Symbol } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'
import { useLanguage } from '../../i18n/useLanguage'
import { t } from '../../i18n/translate'
import { FormulaPicker } from '../FormulaPicker'
import { substitutionGroups, type Inference, type SubstitutionDraft } from './substitutionDraft'

const groups = ['determined', 'identity', 'required'] as const

interface SubstitutionEditorProps {
  inference: Inference
  draft: SubstitutionDraft
  onChange: (next: SubstitutionDraft) => void
  symbolsById: Map<number, Symbol>
  context?: Record<string, number>
}

export function SubstitutionEditor({ inference, draft, onChange, symbolsById, context }: SubstitutionEditorProps) {
  useLanguage()

  // Formula lookups can finish after the user starts editing another row.
  const current = useRef<{ draft: SubstitutionDraft; onChange: SubstitutionEditorProps['onChange'] } | null>(null)
  useLayoutEffect(() => {
    current.current = { draft, onChange }
    return () => { current.current = null }
  }, [draft, onChange])

  function updateDraft(update: (previous: SubstitutionDraft) => SubstitutionDraft) {
    const latest = current.current
    if (!latest) return
    const next = update(latest.draft)
    if (next === latest.draft) return
    current.current = { ...latest, draft: next }
    latest.onChange(next)
  }

  const ids = substitutionGroups(inference)
  const termVars = [...symbolsById.values()].filter((symbol) => symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable)
  const termById = new Map(draft.value.term_substs.map((item) => [item.source_symbol_id, item]))
  const propById = new Map(draft.value.prop_substs.map((item, index) => [item.source_symbol_id, { item, index }]))
  const headings = {
    determined: t('substitutionDetermined', ids.determined.length),
    identity: t('substitutionIdentity', ids.identity.length),
    required: t('substitutionRequired', ids.required.length),
  }
  const localNames = new Map(Object.entries(context ?? {}).map(([name, id]) => [id, name]))
  const nameOf = (id: number) => localNames.get(id) ?? symbolsById.get(id)?.name ?? inference.undetermined.find((item) => item.symbol_id === id)?.name ?? String(id)

  function editText(id: number, unfinished: boolean) {
    updateDraft((previous) => previous.unfinished.includes(id) === unfinished ? previous : {
      ...previous,
      unfinished: unfinished ? [...previous.unfinished, id] : previous.unfinished.filter((item) => item !== id),
    })
  }

  function selectFormula(id: number, formulaId: number) {
    updateDraft((previous) => ({
      unfinished: previous.unfinished.filter((item) => item !== id),
      value: {
        term_substs: previous.value.term_substs.map((item) => item.source_symbol_id === id ? { ...item, target_formula_id: formulaId } : item),
        prop_substs: previous.value.prop_substs.map((item) => item.source_symbol_id === id ? { ...item, body_formula_id: formulaId } : item),
      },
    }))
  }

  function selectParam(index: number, paramIndex: number, id: number) {
    updateDraft((previous) => ({
      ...previous,
      value: {
        ...previous.value,
        prop_substs: previous.value.prop_substs.map((item, i) => i === index
          ? { ...item, formal_param_symbol_ids: item.formal_param_symbol_ids.map((param, j) => j === paramIndex ? id : param) }
          : item),
      },
    }))
  }

  return (
    <div className="space-y-3 rounded border border-slate-200 p-2 text-sm">
      <p className="text-xs text-slate-600">{groups.map((group) => headings[group]).join(' · ')}</p>
      {groups.map((group) => ids[group].length > 0 && (
        <section key={group} aria-label={headings[group]} className="space-y-2">
          {ids[group].map((id) => {
            const term = termById.get(id)
            const prop = propById.get(id)
            if (!term && !prop) return null
            const name = nameOf(id)
            const formulaId = term?.target_formula_id ?? prop?.item.body_formula_id ?? 0
            return (
              <div key={id} role="group" aria-label={name} className="space-y-1 rounded bg-white p-2">
                {group === 'identity' && formulaId === 0 && <p className="text-xs text-slate-600">{t('substitutionKeep', name)}</p>}
                <div className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-start">
                  <div className="flex flex-wrap items-center gap-1 font-medium">
                    <span>{name}</span>
                    {prop && prop.item.formal_param_symbol_ids.length > 0 && (
                      <>
                        <span>(</span>
                        {prop.item.formal_param_symbol_ids.map((param, index, params) => (
                          <span key={index}>
                            {index > 0 && ', '}
                            <select
                              aria-label={t('substitutionParameter', index + 1)}
                              value={param}
                              onChange={(event) => selectParam(prop.index, index, Number(event.target.value))}
                              className="rounded border border-slate-300 px-1 py-0.5 text-xs"
                            >
                              <option value={0} disabled>{t('StepForm_381')}</option>
                              {termVars.map((symbol) => (
                                <option key={symbol.id} value={symbol.id} disabled={param !== symbol.id && params.includes(symbol.id)}>
                                  {nameOf(symbol.id)}
                                </option>
                              ))}
                            </select>
                          </span>
                        ))}
                        <span>)</span>
                      </>
                    )}
                    <span>:=</span>
                  </div>
                  <FormulaPicker
                    key={formulaId}
                    value={formulaId || null}
                    onChange={(selected) => selectFormula(id, selected)}
                    onDraftChange={(unfinished) => editText(id, unfinished)}
                    context={context}
                  />
                </div>
                {prop && prop.item.formal_param_symbol_ids.length > 0 && (
                  <p className="text-xs text-slate-600">{t('substitutionParameterHelp')}</p>
                )}
                {group === 'identity' && formulaId > 0 && (
                  <button type="button" className="text-xs text-indigo-700 underline" onClick={() => selectFormula(id, 0)}>
                    {t('substitutionResetIdentity')}
                  </button>
                )}
                {prop && <ParameterWarning item={prop.item} nameOf={nameOf} />}
              </div>
            )
          })}
        </section>
      ))}
    </div>
  )
}

function ParameterWarning({ item, nameOf }: { item: PropSubst; nameOf: (id: number) => string }) {
  const formulaId = item.body_formula_id
  const { data: body } = useQuery({
    queryKey: ['formulas', formulaId || null],
    queryFn: () => formulasApi.get(formulaId),
    enabled: formulaId > 0 && item.formal_param_symbol_ids.length > 0,
  })
  if (!body) return null
  // Bound occurrences are represented by de Bruijn indices, without a symbol ID.
  const freeIds = new Set(body.tokens.map((token) => token.symbol_id))
  const unused = item.formal_param_symbol_ids.filter((id) => id > 0 && !freeIds.has(id))
  return unused.length > 0 && (
    <p className="text-xs text-amber-700">{t('substitutionUnusedParameters', unused.map(nameOf).join(', '))}</p>
  )
}
