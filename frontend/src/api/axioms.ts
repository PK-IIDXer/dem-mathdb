import { api, buildListQuery, type ListFilter } from './client'
import type { Axiom, AxiomCreate, AxiomSystem, AxiomSystemCreate, Theorem } from './types'

export const axiomsApi = {
  list: (filter?: ListFilter, signal?: AbortSignal) => api.get<Axiom[]>(`/axioms${buildListQuery(filter)}`, { signal }),
  register: (body: AxiomCreate) => api.post<Axiom>('/axioms', body),
  get: (ref: number | string) => api.get<Axiom>(`/axioms/${ref}`),
  getByName: (name: string) => api.get<Axiom>(`/axioms/by-name/${encodeURIComponent(name)}`),
  setDescription: (id: number, description: string | null) =>
    api.patch<Axiom>(`/axioms/${id}/description`, { description }),
  addTag: (id: number, tagId: number) => api.post<Axiom>(`/axioms/${id}/tags`, { tag_id: tagId }),
  removeTag: (id: number, tagId: number) => api.del<Axiom>(`/axioms/${id}/tags/${tagId}`),
  listUsedInTheorems: (id: number) => api.get<Theorem[]>(`/axioms/${id}/used-in-theorems`),

  listSystems: (signal?: AbortSignal) => api.get<AxiomSystem[]>('/axiom-systems', { signal }),
  registerSystem: (body: AxiomSystemCreate) => api.post<AxiomSystem>('/axiom-systems', body),
  getSystem: (id: number) => api.get<AxiomSystem>(`/axiom-systems/${id}`),
  listSystemMembers: (systemId: number) => api.get<Axiom[]>(`/axiom-systems/${systemId}/members`),
  addSystemMember: (systemId: number, axiomId: number) =>
    api.post<void>(`/axiom-systems/${systemId}/members`, { axiom_id: axiomId }),
  removeSystemMember: (systemId: number, axiomId: number) =>
    api.del<void>(`/axiom-systems/${systemId}/members/${axiomId}`),
  isSubsetOf: (childId: number, parentId: number) =>
    api.get<{ is_subset: boolean }>(`/axiom-systems/${childId}/is-subset-of/${parentId}`),
  listSystemProvableTheorems: (systemId: number) => api.get<Theorem[]>(`/axiom-systems/${systemId}/theorems`),
}
