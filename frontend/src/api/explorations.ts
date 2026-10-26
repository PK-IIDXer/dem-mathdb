import { api } from './client'
import type {
  ExplorationDependencies,
  ExplorationNote,
  ExplorationPromotion,
} from './types'

export const explorationsApi = {
  list: () => api.get<ExplorationNote[]>('/explorations'),
  get: (ref: number | string) => api.get<ExplorationNote>(`/explorations/${ref}`),
  create: (body: { name: string; premise_formula_ids: number[] }) =>
    api.post<ExplorationNote>('/explorations', body),
  lineDependencies: (ref: number | string, stepOrd: number) =>
    api.get<ExplorationDependencies>(`/explorations/${ref}/steps/${stepOrd}/dependencies`),
  promote: (ref: number | string, stepOrd: number, name: string) =>
    api.post<ExplorationPromotion>(`/explorations/${ref}/steps/${stepOrd}/promote`, { name }),
}
