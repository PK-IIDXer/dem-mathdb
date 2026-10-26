import { AxiomSystemDetailPage } from './AxiomSystemDetailPage'
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { CommandProvider } from '../commands/CommandProvider'
import { SymbolDetailPage } from './SymbolDetailPage'
import { AxiomDetailPage } from './AxiomDetailPage'
import { TheoremDetailPage } from './TheoremDetailPage'
import { ProofPage } from './ProofPage'
import { DefinitionDetailPage } from './DefinitionDetailPage'
import { ExplorationsPage } from './ExplorationsPage'
import { isPublicId } from '../publicId'

const uuid = '12345678-abcd-4567-89ab-123456789abc'
const routes = [
  ['/axiom-systems/:id', <AxiomSystemDetailPage />],
  ['/symbols/:id', <SymbolDetailPage />],
  ['/axioms/:id', <AxiomDetailPage />],
  ['/theorems/:id', <TheoremDetailPage />],
  ['/theorems/:id/proofs/:proofId', <TheoremDetailPage />],
  ['/proofs/:id', <ProofPage />],
  ['/explorations/:id', <ExplorationsPage />],
  ['/definitions/:id', <DefinitionDetailPage />],
] as const

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function open(pattern: string, path: string, element: React.ReactNode) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}><CommandProvider><Routes>
      <Route path={pattern} element={element} />
    </Routes></CommandProvider></MemoryRouter>
  </QueryClientProvider>)
}

it.each(routes)('rejects numeric and malformed browser references without API calls: %s', (pattern, element) => {
  const fetch = vi.fn(() => Promise.resolve(new Response('{}', { status: 404 })))
  vi.stubGlobal('fetch', fetch)
  for (const ref of ['123', '0', '-1', '1e3', 'not-a-uuid', `${uuid}x`]) {
    open(pattern, pattern.replace(':id', ref).replace(':proofId', uuid), element)
    expect(screen.getByText('見つかりません')).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
    cleanup()
  }
})

it('rejects a numeric nested proof even when the theorem reference is public', () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  open('/theorems/:id/proofs/:proofId', `/theorems/${uuid}/proofs/123`, <TheoremDetailPage />)
  expect(screen.getByText('見つかりません')).toBeTruthy()
  expect(fetch).not.toHaveBeenCalled()
})

it.each(routes)('passes public references to the API: %s', async (pattern, element) => {
  const fetch = vi.fn(() => Promise.resolve(new Response('{}', { status: 404 })))
  vi.stubGlobal('fetch', fetch)
  open(pattern, pattern.replace(':id', uuid).replace(':proofId', uuid), element)
  await waitFor(() => expect(fetch).toHaveBeenCalled())
  expect(fetch.mock.calls.some((args) => String((args as unknown[])[0]).includes(uuid))).toBe(true)
  expect(screen.queryByText('見つかりません')).toBeNull()
})

it('accepts canonical UUIDs independent of case, but not alternate spellings', () => {
  expect(isPublicId(uuid.toUpperCase())).toBe(true)
  for (const ref of [undefined, '', ` ${uuid}`, `{${uuid}}`, uuid.replaceAll('-', ''), `urn:uuid:${uuid}`]) {
    expect(isPublicId(ref)).toBe(false)
  }
})
