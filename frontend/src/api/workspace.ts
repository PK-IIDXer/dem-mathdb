import { api } from './client'

export interface WorkspaceInfo {
  title: string | null
  local_namespace_name: string
}

export const workspaceApi = {
  info: () => api.get<WorkspaceInfo>('/workspace/info'),
}
