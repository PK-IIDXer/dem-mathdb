import { api } from './client'
import type { Formula, FormulaDetail, FormulaParseResult, NamedConclusions, Token } from './types'

/** Mirrors BATCH_MAX_IDS in webapi/routers/formulas.py. */
export const FORMULA_BATCH_MAX_IDS = 500

export interface FormulaSearchResult {
  items: { formula_id: number; bindings: Record<string, unknown> }[]
  next_cursor: string | null
}

export const formulasApi = {
  validate: (tokens: Token[]) => api.post<{ valid: boolean }>('/formulas/validate', { tokens }),
  register: (tokens: Token[], remarks?: string) =>
    api.post<FormulaDetail>('/formulas', { tokens, remarks: remarks ?? null }),
  parse: (text: string, context: Record<string, number> = {}) =>
    api.post<FormulaParseResult>('/formulas/parse', { text, context }),
  print: (tokens: Token[]) => api.post<{ text: string }>('/formulas/print', { tokens }),
  search: (pattern: string, signal?: AbortSignal) => api.post<FormulaSearchResult>(
    '/formulas/search', { pattern, context: {}, limit: 10, cursor: null }, { signal },
  ),
  list: () => api.get<Formula[]>('/formulas'),
  get: (id: number) => api.get<FormulaDetail>(`/formulas/${id}`),
  namedConclusions: (id: number) => api.get<NamedConclusions>(`/formulas/${id}/named-conclusions`),
  /** At most FORMULA_BATCH_MAX_IDS ids; unknown ids are left out of the result. */
  getMany: (ids: number[]) => api.get<FormulaDetail[]>(`/formulas/batch?ids=${ids.join(',')}`),
}
