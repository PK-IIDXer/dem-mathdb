// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { setupUser } from '../test/user'
import { PAGE_INTERACTION_TIMEOUT } from '../test/timeouts'
import { CommandProvider } from '../commands/CommandProvider'
import { ReadOnlyProvider } from '../ReadOnlyContext'
import { AxiomsPage } from './AxiomsPage'
import { TheoremsPage } from './TheoremsPage'
import { DefinitionsPage } from './DefinitionsPage'
import { SymbolsPage } from './SymbolsPage'
import { HomePage } from './HomePage'
import { ProofsPage } from './ProofsPage'

const publicId = '00000000-0000-4000-8000-000000000789'
function mount(element: React.ReactNode, responses: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    return Promise.resolve(new Response(JSON.stringify(url === '/api/config' ? { read_only: true } : responses[url] ?? []), { status: 200 }))
  }))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><CommandProvider><ReadOnlyProvider>{element}</ReadOnlyProvider></CommandProvider></MemoryRouter>
  </QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it.each([['axioms', <AxiomsPage />], ['theorems', <TheoremsPage />], ['definitions', <DefinitionsPage />], ['symbols', <SymbolsPage />]] as const)(
  'keeps the name column and omits the internal id column: %s', async (_, element) => {
    mount(element)
    expect(await screen.findByRole('columnheader', { name: /^name/ })).toBeTruthy()
    expect(screen.queryByRole('columnheader', { name: 'id' })).toBeNull()
  }, PAGE_INTERACTION_TIMEOUT,
)

it('links home axiom systems by public ID', async () => {
  mount(<HomePage />, {
    '/api/axiom-systems': [{ id: 789, public_id: publicId, name: '公開体系' }],
    '/api/stats': {
      theorem_count: 0, proven_theorem_count: 0, verified_proof_count: 0,
      proof_step_count: 0, axiom_count: 0, primitive_axiom_count: 0, axiom_system_count: 1,
      definition_count: 0, dependency_count: 0,
    },
  })
  expect((await screen.findByRole('link', { name: '公開体系' })).getAttribute('href')).toBe(`/axiom-systems/${publicId}`)
}, PAGE_INTERACTION_TIMEOUT)

it('labels proofs by their order rather than their internal ID', async () => {
  mount(<ProofsPage />, {
    '/api/theorems': [{ id: 123, public_id: publicId, name: '対象定理', status: 'proven', tags: [] }],
    '/api/theorems/123/proofs': [{ id: 987, public_id: publicId, name: null, status: 'verified' }],
  })
  await screen.findByRole('option', { name: /対象定理/ })
  await setupUser().selectOptions(screen.getByRole('combobox'), '123')
  expect(await screen.findByRole('link', { name: /証明 1/ })).toBeTruthy()
  expect(screen.queryByText(/#987/)).toBeNull()
}, PAGE_INTERACTION_TIMEOUT)
