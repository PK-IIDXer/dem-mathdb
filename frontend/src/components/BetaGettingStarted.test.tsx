// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ReadOnlyProvider } from '../ReadOnlyContext'
import { BetaGettingStarted } from './BetaGettingStarted'
import { ONBOARDING_AXIOMS, ONBOARDING_PREDICATE } from '../onboarding'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import type { Symbol } from '../api/types'
import type { Config } from '../api/config'

// Synthetic prerequisite responses; no private corpus or proof fixture is needed.
const symbols: Symbol[] = [
  { name: ONBOARDING_PREDICATE, arity: 1, type: SYMBOL_TYPE.freePropositionVariable },
  { name: 'x', arity: 0, type: SYMBOL_TYPE.freeTermVariable },
  { name: '→', arity: 2, type: SYMBOL_TYPE.logical },
  { name: '∀', arity: 1, type: SYMBOL_TYPE.logical },
].map(({ name, arity, type }, index) => ({
  id: index + 1, public_id: `synthetic-symbol-${index}`, name, arity,
  symbol_type_id: index + 1,
  symbol_type: { id: index + 1, name: type, output_formula_type_id: 1,
    input_formula_type_id: null, fixed_arity: arity, is_quantifier: name === '∀',
    remarks: null, created_at: '2000-01-01T00:00:00Z' },
  is_primitive: true, namespace_id: 1, namespace_name: 'synthetic',
  notation_kind: 'prefix', precedence: null, latex_template: null,
  remarks: null, created_at: '2000-01-01T00:00:00Z',
}))
const axioms = ONBOARDING_AXIOMS.map((name, index) => ({ name, id: index + 1, formula_id: index + 1 }))
const open: Config = { read_only: false, beta: { enabled: true, write_state: 'open', next_reset_at: null, last_reset_at: null, last_reset_error: null, limits: {} } }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
function setup(config = open, missing = '') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['config'], config)
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace('/api', '')
    expect(init?.method ?? 'GET').toBe('GET')
    let data: unknown
    if (missing === 'network') throw new Error('offline')
    if (path.startsWith('/axioms/by-name/')) {
      const name = path.split('/').at(-1)
      if (name === missing) return new Response('{}', { status: 404 })
      data = axioms.find(item => item.name === name)
    } else if (path === '/symbols') {
      data = symbols.map(s => s.name === ONBOARDING_PREDICATE && missing === 'arity' ? { ...s, arity: 0 } : s.name === ONBOARDING_PREDICATE && missing === 'type' ? { ...s, symbol_type: { ...s.symbol_type, name: SYMBOL_TYPE.logical } } : s).filter(s => missing !== s.name && !(missing === 'variable' && s.symbol_type.name === SYMBOL_TYPE.freeTermVariable))
    } else if (path.startsWith('/symbol-roles/')) {
      if (path.endsWith(missing) && missing) return new Response('{}', { status: 404 })
      data = symbols.find(s => s.name === (path.endsWith('implication') ? '→' : '∀'))
    } else throw new Error('unexpected ' + path)
    return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetcher)
  const show = () => render(<QueryClientProvider client={client}><ReadOnlyProvider><MemoryRouter><BetaGettingStarted theorems={[]} /></MemoryRouter></ReadOnlyProvider></QueryClientProvider>)
  return { client, fetcher, show }
}
it('offers an opt-in link with accurate shared-storage and display scope using five cached GETs', async () => {
  const { client, fetcher, show } = setup()
  const view = show()
  const link = await screen.findByRole('link', { name: 'チュートリアルを始める' })
  expect(link.getAttribute('href')).toBe('/formulas?onboarding=1')
  expect(screen.getByText(/共有データベースに保存されます/).textContent).toContain('数式と直接 URL は共有されます')
  expect(screen.getByText(/毎週月曜 4:00/)).toBeTruthy()
  expect(fetcher).toHaveBeenCalledTimes(5)
  view.unmount(); show()
  expect(await screen.findByRole('link', { name: 'チュートリアルを始める' })).toBeTruthy()
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(fetcher).toHaveBeenCalledTimes(5)
  expect(screen.queryByText('式を書いてみる')).toBeNull()
})
it.each([
  { read_only: true, beta: open.beta }, { read_only: false },
  { read_only: false, beta: { ...open.beta!, write_state: 'maintenance' as const } },
  { read_only: false, beta: { ...open.beta!, write_state: 'full' as const } },
])('hides the entire entry and makes no prerequisite request for %j', async config => {
  const { fetcher, show } = setup(config)
  show()
  expect(screen.queryByRole('region', { name: 'βのチュートリアル' })).toBeNull()
  expect(fetcher).not.toHaveBeenCalled()
})
it.each([...ONBOARDING_AXIOMS, ONBOARDING_PREDICATE, 'arity', 'type', 'variable', 'implication', 'universal_quantifier', 'network'])('fails closed for missing/failed prerequisite %s', async missing => {
  const { client, show } = setup(open, missing)
  show()
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(screen.queryByRole('region', { name: 'βのチュートリアル' })).toBeNull()
})

it('rechecks after a reset and hides cached success if the new check fails', async () => {
  const { client, fetcher, show } = setup()
  show()
  await screen.findByRole('link', { name: 'チュートリアルを始める' })
  expect(fetcher).toHaveBeenCalledTimes(5)
  fetcher.mockRejectedValue(new Error('offline after reset'))
  act(() => client.setQueryData(['config'], { ...open, beta: { ...open.beta!, last_reset_at: '2026-11-01T19:00:00Z' } }))
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(10))
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(screen.queryByRole('region', { name: 'βのチュートリアル' })).toBeNull()
})

it('also hides a previously visible beta entry when refreshing configuration fails', async () => {
  const { client, show } = setup()
  show()
  await screen.findByRole('link', { name: 'チュートリアルを始める' })
  act(() => { client.getQueryCache().find({ queryKey: ['config'] })!.setState({ status: 'error', error: new Error('configuration unavailable') }) })
  await waitFor(() => expect(screen.queryByRole('region', { name: 'βのチュートリアル' })).toBeNull())
})
