import { api } from './client'

export interface Stats {
  theorem_count: number
  proven_theorem_count: number
  verified_proof_count: number
  proof_step_count: number
  axiom_count: number
  primitive_axiom_count: number
  axiom_system_count: number
  definition_count: number
  dependency_count: number
}

export const statsApi = {
  get: () => api.get<Stats>('/stats'),
}
