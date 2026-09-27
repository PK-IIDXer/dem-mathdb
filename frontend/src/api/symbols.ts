import { api } from './client'
import type { FormulaType, NotationKind, Symbol, SymbolAlias, SymbolCreate, SymbolType } from './types'

export const symbolsApi = {
  listFormulaTypes: () => api.get<FormulaType[]>('/formula-types'),
  listSymbolTypes: () => api.get<SymbolType[]>('/symbol-types'),
  listSymbols: (symbolTypeId?: number, withUsage = false, signal?: AbortSignal) => {
    const params = new URLSearchParams()
    if (symbolTypeId != null) params.set('symbol_type_id', String(symbolTypeId))
    if (withUsage) params.set('with_usage', 'true')
    const query = params.toString()
    return api.get<Symbol[]>(`/symbols${query ? `?${query}` : ''}`, { signal })
  },
  register: (body: SymbolCreate) => api.post<Symbol>('/symbols', body),
  get: (ref: number | string) => api.get<Symbol>(`/symbols/${ref}`),
  getByRole: (role: string) => api.get<Symbol>(`/symbol-roles/${role}`),
  setNotation: (id: number, notationKind: NotationKind, precedence?: number | null) =>
    api.patch<Symbol>(`/symbols/${id}/notation`, {
      notation_kind: notationKind,
      precedence: precedence ?? null,
    }),
  setLatexTemplate: (id: number, latexTemplate: string | null) =>
    api.patch<Symbol>(`/symbols/${id}/latex-template`, {
      latex_template: latexTemplate,
    }),
  listAliases: () => api.get<SymbolAlias[]>('/symbol-aliases'),
  addAlias: (id: number, alias: string) =>
    api.post<SymbolAlias>(`/symbols/${id}/aliases`, { alias }),
}
