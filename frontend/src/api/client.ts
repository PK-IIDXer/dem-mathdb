export class ApiError extends Error {
  status: number
  body: unknown
  position: number | null

  constructor(status: number, body: unknown) {
    super(extractMessage(body))
    this.status = status
    this.body = body
    this.position = extractPosition(body)
  }
}

function extractMessage(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : JSON.stringify(item)))
        .join('; ')
    }
  }
  return 'Unknown API error'
}

function extractPosition(body: unknown): number | null {
  if (body && typeof body === 'object' && 'position' in body) {
    const position = (body as { position: unknown }).position
    return typeof position === 'number' ? position : null
  }
  return null
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, options?: Pick<RequestInit, 'signal'>) => request<T>(path, options),
  post: <T>(path: string, body: unknown, options?: Pick<RequestInit, 'signal'>) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body), ...options }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

export interface ListFilter {
  search?: string
  tagIds?: number[]
  excludeTagIds?: number[]
  status?: string
}

export function buildListQuery(filter?: ListFilter): string {
  const params = new URLSearchParams()
  if (filter?.search) params.set('search', filter.search)
  for (const tagId of filter?.tagIds ?? []) params.append('tag_id', String(tagId))
  for (const tagId of filter?.excludeTagIds ?? []) params.append('exclude_tag_id', String(tagId))
  if (filter?.status) params.set('status', filter.status)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}
