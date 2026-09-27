import { api, buildListQuery, type ListFilter } from './client'
import { tagsApi } from './tags'
import type { ApplicableTheorem, Tag, Theorem, TheoremCreate, TheoremPremise } from './types'
import { ONBOARDING_TAG_NAME } from '../onboarding'

export const theoremsApi = {
  list: (filter?: ListFilter, signal?: AbortSignal) => api.get<Theorem[]>(`/theorems${buildListQuery(filter)}`, { signal }),
  listRules: (signal?: AbortSignal) => api.get<Theorem[]>('/theorems/rules', { signal }),
  /** `loadTags` finds the onboarding tag to exclude. Callers that run this per
   * search should pass one that goes through the ['tags'] query (e.g.
   * `queryClient.fetchQuery`), so a fresh cached list is reused and an
   * invalidated one is refetched; the tag list is large, and fetching it again
   * for each search is wasted. */
  listVisible: async (filter?: ListFilter, loadTags: () => Promise<Tag[]> = tagsApi.list) => {
    const tags = await loadTags()
    const onboardingTagId = tags.find((tag) => tag.name === ONBOARDING_TAG_NAME)?.id
    return api.get<Theorem[]>(`/theorems${buildListQuery({
      ...filter,
      excludeTagIds: onboardingTagId == null
        ? filter?.excludeTagIds
        : [...(filter?.excludeTagIds ?? []), onboardingTagId],
    })}`)
  },
  register: (body: TheoremCreate) => api.post<Theorem>('/theorems', body),
  get: (ref: number | string) => api.get<Theorem>(`/theorems/${ref}`),
  listPremises: (id: number) => api.get<TheoremPremise[]>(`/theorems/${id}/premises`),
  setDescription: (id: number, description: string | null) =>
    api.patch<Theorem>(`/theorems/${id}/description`, { description }),
  addTag: (id: number, tagId: number) =>
    api.post<Theorem>(`/theorems/${id}/tags`, { tag_id: tagId }),
  removeTag: (id: number, tagId: number) => api.del<Theorem>(`/theorems/${id}/tags/${tagId}`),
  listUsedInTheorems: (id: number) => api.get<Theorem[]>(`/theorems/${id}/used-in-theorems`),
  listApplicable: ({
    goalFormulaId,
    proofId,
    argStepOrds = [],
    limit = 20,
  }: {
    goalFormulaId?: number | null
    proofId?: number
    argStepOrds?: number[]
    limit?: number
  }) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (goalFormulaId != null) params.set('goal_formula_id', String(goalFormulaId))
    if (proofId != null) params.set('proof_id', String(proofId))
    if (argStepOrds.length > 0) params.set('arg_step_ords', argStepOrds.join(','))
    return api.get<ApplicableTheorem[]>(`/theorems/applicable?${params}`)
  },
}
