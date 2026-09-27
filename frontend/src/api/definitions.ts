import { api, buildListQuery, type ListFilter } from './client'
import type { Axiom, Definition, DefinitionCreate, Symbol } from './types'

export const definitionsApi = {
  list: (filter?: ListFilter, signal?: AbortSignal) => api.get<Definition[]>(`/definitions${buildListQuery(filter)}`, { signal }),
  register: (body: DefinitionCreate) => api.post<Definition>('/definitions', body),
  get: (ref: number | string) => api.get<Definition>(`/definitions/${ref}`),
  getSymbol: (id: number) => api.get<Symbol>(`/definitions/${id}/symbol`),
  getAxiom: (id: number) => api.get<Axiom>(`/definitions/${id}/axiom`),
  listFormalParams: (id: number) => api.get<Symbol[]>(`/definitions/${id}/formal-params`),
  setDescription: (id: number, description: string | null) =>
    api.patch<Definition>(`/definitions/${id}/description`, { description }),
  addTag: (id: number, tagId: number) =>
    api.post<Definition>(`/definitions/${id}/tags`, { tag_id: tagId }),
  removeTag: (id: number, tagId: number) => api.del<Definition>(`/definitions/${id}/tags/${tagId}`),
}
