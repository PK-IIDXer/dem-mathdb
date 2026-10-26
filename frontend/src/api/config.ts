import { api } from './client'

export interface Config {
  read_only: boolean
  beta?: BetaConfig
}

export interface BetaConfig {
  enabled: boolean
  write_state: 'open' | 'maintenance' | 'full'
  next_reset_at: string | null
  last_reset_at: string | null
  last_reset_error: { failed_at: string; stage: string } | null
  limits: Record<string, number>
}

export const configApi = {
  get: () => api.get<Config>('/config'),
}
