// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const theoremId = '11111111-1111-4111-8111-111111111111'
const proofId = '22222222-2222-4222-8222-222222222222'
const base = '/public-data/' + 'a'.repeat(64)
const route = `/theorems/${theoremId}/proofs/${proofId}`
const theorem = { id: 1, public_id: theoremId, name: 'theorem' }
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  vi.resetModules()
  document.head.innerHTML = `<meta name="dem-public-data" content="${base}">`
  window.history.replaceState({}, '', route)
})
afterEach(() => { vi.unstubAllGlobals(); document.head.innerHTML = '' })

async function setup(mode = true, kind = 'ok') {
  const fetcher = vi.fn(async (url: string) => {
    if (url === '/api/config') return json({ read_only: mode })
    if (url.startsWith('/api/')) return json({ live: true, ...theorem })
    if (kind === 'error') throw new Error('offline')
    if (kind === 'html') return new Response('<html></html>', { headers: { 'Content-Type': 'text/html' } })
    if (kind === 'broken') return new Response('{', { headers: { 'Content-Type': 'application/json' } })
    if (kind === '404') return new Response('', { status: 404 })
    if (kind === 'array') return json([])
    return json(url.endsWith('common.json')
      ? { '/config': { read_only: true }, '/symbols': [{ id: 1 }], '/tags': [] }
      : { [`/theorems/${theoremId}`]: theorem, '/theorems/1': theorem,
          '/proofs/2': { status: 'verified' }, '/proofs/2/direct-dependencies': { lemmas: [] },
          '/proofs/2/formulas': [{ id: 3, text: 'formula' }], '/proofs/2/is-valid-in-system/4': { valid: false },
          '/formulas/batch?ids=1,2': [{ id: 1 }, { id: 2 }] })
  })
  vi.stubGlobal('fetch', fetcher)
  const { startPublicData } = await import('./publicData')
  const { api } = await import('./client')
  startPublicData()
  // Eager common + proof requests start without waiting for /config.
  if (document.querySelector('meta')) expect(fetcher.mock.calls.length).toBe(2)
  await api.get('/config')
  return { api, fetcher }
}

describe('deployment response data', () => {
  it('shares deeply frozen values without allowing later reads to be corrupted', async () => {
    const { api } = await setup()
    const first = await api.get<{ status: string }>('/proofs/2')
    expect(await api.get('/proofs/2')).toBe(first)
    expect(() => { first.status = 'draft' }).toThrow(TypeError)
    const formulas = await api.get<{ id: number }[]>('/formulas/batch?ids=1,2')
    expect(() => { formulas[0].id = 999 }).toThrow(TypeError)
    expect(() => formulas.push({ id: 3 })).toThrow(TypeError)
    expect(await api.get('/proofs/2')).toEqual({ status: 'verified' })
    expect(await api.get('/formulas/batch?ids=1,2')).toEqual([{ id: 1 }, { id: 2 }])
  })

  it('serves exact paths including queries without data API requests', async () => {
    const { api, fetcher } = await setup()
    expect(await api.get(`/theorems/${theoremId}`)).toEqual(theorem)
    expect(await api.get('/proofs/2')).toEqual({ status: 'verified' })
    expect(await api.get('/formulas/batch?ids=1,2')).toEqual([{ id: 1 }, { id: 2 }])
    expect(await api.get('/symbols')).toEqual([{ id: 1 }])
    expect(fetcher.mock.calls.filter(([url]) => url.startsWith('/api/')).map(([url]) => url)).toEqual(['/api/config'])
    await api.get('/not-in-bundle')
    expect(fetcher).toHaveBeenCalledWith('/api/not-in-bundle', expect.anything())
  })

  it.each(['html', 'broken', 'error', '404', 'array'])('silently falls back for %s', async kind => {
    const { api, fetcher } = await setup(true, kind)
    expect(await api.get('/proofs/2')).toHaveProperty('live', true)
    expect(fetcher).toHaveBeenCalledWith('/api/proofs/2', expect.anything())
  })

  it('uses normal requests with no deployment meta', async () => {
    document.head.innerHTML = ''
    const { api, fetcher } = await setup()
    expect(await api.get('/proofs/2')).toHaveProperty('live', true)
    expect(fetcher.mock.calls.every(([url]) => url.startsWith('/api/'))).toBe(true)
  })

  it('does not trust bundled config on an editable deployment or reuse edited data', async () => {
    const { api, fetcher } = await setup(false)
    expect(await api.get('/proofs/2')).toHaveProperty('live', true)
    await api.get('/symbols')
    await api.patch('/symbols/1', { name: 'changed' })
    await api.get('/symbols')
    await api.get(`/theorems/${theoremId}`)
    await api.get('/theorems/1')
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/symbols')).toHaveLength(2)
    expect(fetcher).toHaveBeenCalledWith('/api/theorems/1', expect.anything())
  })

  it('deduplicates symbols, dependencies and public/internal theorem reads without bundles', async () => {
    document.head.innerHTML = ''
    const { api, fetcher } = await setup()
    await api.get(`/theorems/${theoremId}`)
    await api.get('/theorems/1')
    await Promise.all([api.get('/symbols'), api.get('/symbols')])
    await api.get('/symbols')
    await api.get('/proofs/2/direct-dependencies')
    await api.get('/proofs/2/direct-dependencies')
    const urls = fetcher.mock.calls.map(([url]) => url)
    expect(urls).not.toContain('/api/theorems/1')
    expect(urls.filter(url => url === '/api/symbols')).toHaveLength(1)
    expect(urls.filter(url => url === '/api/proofs/2/direct-dependencies')).toHaveLength(1)
  })

  it('clears live reuse and disables snapshots when config changes to editable', async () => {
    const { api, fetcher } = await setup()
    await api.get('/symbols')
    fetcher.mockImplementation(async () => json({ read_only: false, changed: true }))
    await api.get('/config')
    expect(await api.get('/symbols')).toHaveProperty('changed', true)
  })

  it('loads a different proof after client-side navigation and falls back for absent keys', async () => {
    const { api, fetcher } = await setup()
    const next = '33333333-3333-4333-8333-333333333333'
    window.history.replaceState({}, '', `/theorems/${theoremId}/proofs/${next}`)
    await api.get('/proofs/3')
    expect(fetcher).toHaveBeenCalledWith(`${base}/proofs/${theoremId}/${next}.json`, expect.anything())
    expect(fetcher).toHaveBeenCalledWith('/api/proofs/3', expect.anything())
  })
})
