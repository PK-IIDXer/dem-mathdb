import { api } from './client'

export interface Config {
  read_only: boolean
}

export const configApi = {
  get: () => api.get<Config>('/config'),
}
