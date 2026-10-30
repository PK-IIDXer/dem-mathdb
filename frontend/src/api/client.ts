import { publicResponse, setPublicReadOnly } from './publicData'
import { errorGuidance, retrySeconds } from './errorGuidance'

const writeErrors = new Set<(error: ApiError) => void>()
export function subscribeWriteErrors(listener: (error: ApiError) => void) {
  writeErrors.add(listener)
  return () => { writeErrors.delete(listener) }
}

export class ApiError extends Error {
  status: number
  body: unknown
  position: number | null
  retryAfter: number | null
  guidance: boolean

  constructor(status: number, body: unknown, retryAfter: string | null = null) {
    const retry = retrySeconds(retryAfter)
    const guidance = errorGuidance(status, body, retry)
    super(guidance ?? extractMessage(body))
    this.retryAfter = retry
    this.guidance = guidance != null
    this.status = status
    this.body = body
    this.position = extractPosition(body)
    Object.defineProperty(this, 'message', { configurable: true, get: () => errorGuidance(this.status, this.body, this.retryAfter) ?? extractMessage(this.body) })
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

async function networkRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const error = new ApiError(response.status, body, response.headers?.get('Retry-After') ?? null)
    if (options?.method && options.method !== 'GET' && error.guidance) {
      for (const listener of writeErrors) listener(error)
    }
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

let readOnly = false
const reads = new Map<string, Promise<unknown>>()

// Only reuse live responses on an immutable, read-only deployment. This also
// avoids duplicate requests when no static build is present. Editable views
// retain their normal React Query invalidation and network behavior.
function reusable(path: string): boolean {
  return path === '/symbols' || /^\/proofs\/\d+\/direct-dependencies$/.test(path)
    || /^\/theorems\/(?:\d+|[0-9a-f-]{36})$/.test(path)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  if (options?.method && options.method !== 'GET') return networkRequest<T>(path, options)
  if (path === '/config') {
    // Never trust the copy of config in the bundle to authorize caching.
    try {
      const value = await networkRequest<{ read_only: boolean }>(path, options)
      readOnly = value.read_only === true
      setPublicReadOnly(readOnly)
      if (!readOnly) reads.clear()
      return value as T
    } catch (error) {
      readOnly = false
      setPublicReadOnly(false)
      reads.clear()
      throw error
    }
  }
  const canReuse = readOnly && !options?.signal && reusable(path)
  if (canReuse && reads.has(path)) return await reads.get(path) as T
  const result = (async () => {
    const snapshot = await publicResponse(path)
    if (snapshot.found) return snapshot.value as T
    return networkRequest<T>(path, options)
  })()
  if (canReuse) {
    reads.set(path, result)
    try {
      const value = await result
      // Public and internal references resolve to the same theorem response.
      if (readOnly && reads.get(path) === result && path.startsWith('/theorems/')) {
        const theorem = value as { id?: number; public_id?: string }
        if (typeof theorem.id === 'number' && typeof theorem.public_id === 'string') {
          reads.set(`/theorems/${theorem.id}`, result)
          reads.set(`/theorems/${theorem.public_id}`, result)
        }
      }
      return value
    } catch (error) {
      if (reads.get(path) === result) reads.delete(path)
      throw error
    }
  }
  return result
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
