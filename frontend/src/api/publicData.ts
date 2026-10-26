/** Optional deployment snapshots. Live /config is the authority for read-only
 * mode; a stale HTML file must never enable these on an editable deployment. */
type ResponseMap = Record<string, unknown>
const missing = { found: false } as const
let readOnly = false
let base: string | null = null
let common: Promise<ResponseMap | null> | null = null
let currentPath = ''
let proof: Promise<ResponseMap | null> | null = null

/** Snapshot values are immutable, just like their content-addressed files.
 * Freeze lazily on first use so repeated reads can share them safely. */
function freeze(value: unknown): unknown {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) freeze(child)
    Object.freeze(value)
  }
  return value
}

async function load(path: string): Promise<ResponseMap | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 3000)
  try {
    const response = await fetch(path, { signal: controller.signal })
    if (!response.ok || response.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') return null
    const value: unknown = await response.json()
    return value != null && typeof value === 'object' && !Array.isArray(value) ? value as ResponseMap : null
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

function startProof() {
  const path = window.location.pathname.replace(/\/$/, '')
  if (path === currentPath) return
  currentPath = path
  const match = /^\/theorems\/([0-9a-f-]{36})\/proofs\/([0-9a-f-]{36})$/.exec(path)
  proof = base && match ? load(`${base}/proofs/${match[1]}/${match[2]}.json`) : null
}

export function startPublicData() {
  const value = document.querySelector<HTMLMetaElement>('meta[name="dem-public-data"]')?.content
  if (!value || !/^\/public-data\/[0-9a-f]{64}$/.test(value)) return
  base = value
  common ??= load(`${base}/common.json`)
  startProof()
}

export function setPublicReadOnly(value: boolean) {
  readOnly = value
}

export async function publicResponse(path: string): Promise<{ found: true; value: unknown } | typeof missing> {
  if (!readOnly || !base) return missing
  startProof()
  // Common values need not wait for a large proof payload.
  for (const pending of [common, proof]) {
    const responses = await pending
    if (!readOnly) return missing
    if (responses && Object.hasOwn(responses, path)) return { found: true, value: freeze(responses[path]) }
  }
  return missing
}
