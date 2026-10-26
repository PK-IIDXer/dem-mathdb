// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { HomePage } from './HomePage'

const values = {
  theorem_count: 1234, proven_theorem_count: 987, verified_proof_count: 999,
  proof_step_count: 45678, axiom_count: 234, primitive_axiom_count: 156, axiom_system_count: 56,
  definition_count: 78, dependency_count: 8901,
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function showHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['theorems'], [])
  client.setQueryData(['tags'], [])
  client.setQueryData(['axiomSystems'], [])
  return render(<QueryClientProvider client={client}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)
}

it('displays corpus counts from the stats API rather than the theorem list', async () => {
  const fetcher = vi.fn(async (url: string) => ({ ok: true, json: async () => url === '/api/stats' ? values : [] }))
  vi.stubGlobal('fetch', fetcher)
  showHome()
  const region = screen.getByRole('region', { name: '収録規模' })
  for (const [label, value] of [
    ['登録済みの定理', '1,234'], ['証明済み', '987'], ['証明ステップ', '45,678'],
    ['原始公理', '156'], ['公理系', '56'], ['定理間の依存', '8,901'],
  ]) {
    await waitFor(() => expect(within(region).getByText(label).parentElement?.textContent).toContain(value))
  }
  expect(fetcher.mock.calls.some(([url]) => url === '/api/stats')).toBe(true)
  expect(document.title).toBe('Deus Ex Machina')
})

it('does not present failed counts as zero', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
  showHome()
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(within(screen.getByRole('region', { name: '収録規模' })).getAllByText('—')).toHaveLength(6)
})
