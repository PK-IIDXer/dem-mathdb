import { setupUser } from '../test/user'
import { PAGE_INTERACTION_TIMEOUT } from '../test/timeouts'
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { DependencyGraph } from './DependencyGraph'
import { AxiomsPage } from '../pages/AxiomsPage'
import { proofsApi } from '../api/proofs'
import { axiomsApi } from '../api/axioms'
import type { Axiom, AxiomSystem, Proof, Theorem } from '../api/types'

const axiom = { id: 123, public_id: '00000000-0000-4000-8000-000000000001', name: '公理の名前', tags: [] } as unknown as Axiom
const theorem = { id: 456, public_id: '00000000-0000-4000-8000-000000000002', name: '定理の名前', status: 'proven' } as Theorem
function mount(element: React.ReactNode) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter>{element}</MemoryRouter>
  </QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('links dependency axioms and theorems by public ID', async () => {
  vi.spyOn(proofsApi, 'listForTheorem').mockResolvedValue([{ id: 7, status: 'verified' } as Proof])
  vi.spyOn(proofsApi, 'listDirectDependencies').mockResolvedValue({ axioms: [axiom], lemmas: [{ proof_id: 8, theorem }] })
  mount(<DependencyGraph theoremId={1} />)
  expect((await screen.findByRole('link', { name: '公理 公理の名前' })).getAttribute('href')).toBe(`/axioms/${axiom.public_id}`)
  expect(screen.getByRole('link', { name: theorem.name }).getAttribute('href')).toBe(`/theorems/${theorem.public_id}`)
})

it('shows axiom names without internal IDs and system names without internal IDs', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('[]', { status: 200 }))))
  vi.spyOn(axiomsApi, 'list').mockResolvedValue([axiom])
  vi.spyOn(axiomsApi, 'listSystems').mockResolvedValue([{ id: 789, public_id: '00000000-0000-4000-8000-000000000789', name: '体系の名前' } as AxiomSystem])
  vi.spyOn(axiomsApi, 'listSystemMembers').mockResolvedValue([axiom])
  mount(<AxiomsPage />)
  await setupUser().click(await screen.findByRole('button', { name: '体系の名前' }))
  expect((await screen.findAllByText(axiom.name)).length).toBeGreaterThan(0)
  expect(screen.queryByText('#123 公理の名前')).toBeNull()
  expect(screen.queryByText('#789 体系の名前')).toBeNull()
  expect(screen.queryByRole('columnheader', { name: 'id' })).toBeNull()
  expect(screen.getByRole('link', { name: '詳細' }).getAttribute('href')).toBe('/axiom-systems/00000000-0000-4000-8000-000000000789')
}, PAGE_INTERACTION_TIMEOUT)
