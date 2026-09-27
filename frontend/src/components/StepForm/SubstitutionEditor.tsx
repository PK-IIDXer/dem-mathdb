import { useQuery } from '@tanstack/react-query'
import { symbolsApi } from '../../api/symbols'
import { FormulaPicker } from '../FormulaPicker'
import type { PropSubst, Substitution, TermSubst } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'

interface SubstitutionEditorProps {
  value: Substitution
  onChange: (next: Substitution) => void
  editableSymbolIds?: number[]
  context?: Record<string, number>
}

/** Builds a dem.types.Substitution: a set of term-free-variable substitutions
 * (x -> term formula) and proposition-free-variable substitutions (phi ->
 * (body formula, ordered formal params)). Mirrors PropSubst/TermSubst 1:1. */
export function SubstitutionEditor({ value, onChange, editableSymbolIds, context }: SubstitutionEditorProps) {
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const termVars = symbols.filter((s) => s.symbol_type.name === SYMBOL_TYPE.freeTermVariable)
  const propVars = symbols.filter((s) => s.symbol_type.name === SYMBOL_TYPE.freePropositionVariable)
  const editable = editableSymbolIds ? new Set(editableSymbolIds) : null
  const visibleTermSubsts = value.term_substs
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => editable == null || editable.has(item.source_symbol_id))
  const visiblePropSubsts = value.prop_substs
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => editable == null || editable.has(item.source_symbol_id))

  function updateTermSubst(index: number, patch: Partial<TermSubst>) {
    const next = value.term_substs.map((item, i) => (i === index ? { ...item, ...patch } : item))
    onChange({ ...value, term_substs: next })
  }
  function updatePropSubst(index: number, patch: Partial<PropSubst>) {
    const next = value.prop_substs.map((item, i) => (i === index ? { ...item, ...patch } : item))
    onChange({ ...value, prop_substs: next })
  }

  return (
    <div className="space-y-3 rounded border border-slate-200 p-2 text-sm">
      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
          <span>項型自由変数への代入 (term_substs)</span>
          {editable == null && <button
            type="button"
            className="rounded bg-slate-100 px-2 py-0.5 text-xs hover:bg-slate-200"
            onClick={() =>
              onChange({
                ...value,
                term_substs: [
                  ...value.term_substs,
                  { source_symbol_id: termVars[0]?.id ?? 0, target_formula_id: 0 },
                ],
              })
            }
          >
            + 追加
          </button>}
        </div>
        {visibleTermSubsts.map(({ item, index }) => (
          <div key={index} className="mb-2 flex items-start gap-2">
            <select
              value={item.source_symbol_id}
              onChange={(e) => updateTermSubst(index, { source_symbol_id: Number(e.target.value) })}
              className="rounded border border-slate-300 px-1 py-1 text-xs"
            >
              {termVars.map((sym) => (
                <option key={sym.id} value={sym.id}>
                  {sym.name}
                </option>
              ))}
            </select>
            <span className="mt-1 text-xs text-slate-400">↦</span>
            <div className="flex-1">
              <FormulaPicker
                value={item.target_formula_id || null}
                onChange={(id) => updateTermSubst(index, { target_formula_id: id })}
                context={context}
              />
            </div>
            {editable == null && <button
              type="button"
              onClick={() =>
                onChange({ ...value, term_substs: value.term_substs.filter((_, i) => i !== index) })
              }
              className="text-slate-400 hover:text-red-600"
            >
              ×
            </button>}
          </div>
        ))}
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
          <span>命題型自由変数への代入 (prop_substs)</span>
          {editable == null && <button
            type="button"
            className="rounded bg-slate-100 px-2 py-0.5 text-xs hover:bg-slate-200"
            onClick={() =>
              onChange({
                ...value,
                prop_substs: [
                  ...value.prop_substs,
                  { source_symbol_id: propVars[0]?.id ?? 0, body_formula_id: 0, formal_param_symbol_ids: [] },
                ],
              })
            }
          >
            + 追加
          </button>}
        </div>
        {visiblePropSubsts.map(({ item, index }) => (
          <div key={index} className="mb-2 space-y-1 rounded bg-slate-50 p-2">
            <div className="flex items-start gap-2">
              <select
                value={item.source_symbol_id}
                onChange={(e) => updatePropSubst(index, { source_symbol_id: Number(e.target.value) })}
                className="rounded border border-slate-300 px-1 py-1 text-xs"
              >
                {propVars.map((sym) => (
                  <option key={sym.id} value={sym.id}>
                    {sym.name} (arity {sym.arity})
                  </option>
                ))}
              </select>
              <span className="mt-1 text-xs text-slate-400">↦ body:</span>
              <div className="flex-1">
                <FormulaPicker
                  value={item.body_formula_id || null}
                  onChange={(id) => updatePropSubst(index, { body_formula_id: id })}
                  context={context}
                />
              </div>
              {editable == null && <button
                type="button"
                onClick={() =>
                  onChange({ ...value, prop_substs: value.prop_substs.filter((_, i) => i !== index) })
                }
                className="text-slate-400 hover:text-red-600"
              >
                ×
              </button>}
            </div>
            <div className="flex items-center gap-1 pl-1">
              <span className="text-xs text-slate-400">formal params (順序あり):</span>
              {item.formal_param_symbol_ids.map((paramId, paramIndex) => (
                <span key={paramIndex} className="flex items-center gap-0.5">
                  <select
                    value={paramId}
                    onChange={(e) => {
                      const params = [...item.formal_param_symbol_ids]
                      params[paramIndex] = Number(e.target.value)
                      updatePropSubst(index, { formal_param_symbol_ids: params })
                    }}
                    className="rounded border border-slate-300 px-1 py-0.5 text-xs"
                  >
                    {termVars.map((sym) => (
                      <option key={sym.id} value={sym.id}>
                        {sym.name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      const params = item.formal_param_symbol_ids.filter((_, i) => i !== paramIndex)
                      updatePropSubst(index, { formal_param_symbol_ids: params })
                    }}
                    className="text-slate-400 hover:text-red-600"
                  >
                    ×
                  </button>
                </span>
              ))}
              <button
                type="button"
                onClick={() =>
                  updatePropSubst(index, {
                    formal_param_symbol_ids: [...item.formal_param_symbol_ids, termVars[0]?.id ?? 0],
                  })
                }
                className="rounded bg-slate-200 px-1.5 py-0.5 text-xs hover:bg-slate-300"
              >
                +
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
