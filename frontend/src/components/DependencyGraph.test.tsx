// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Axiom, DirectDependencies, Proof, Theorem } from '../api/types'
import { DependencyGraph } from './DependencyGraph'

function theorem(id: number, name: string): Theorem {
  return { id, name, status: 'proven' } as unknown as Theorem
}

function proof(id: number, theoremId: number): Proof {
  return { id, theorem_id: theoremId, status: 'verified' } as unknown as Proof
}

const ROOT = theorem(1, 'root_theorem')
const LEMMA_A = theorem(2, 'lemma_a')
const LEMMA_B = theorem(3, 'lemma_b')
const LEMMA_C = theorem(4, 'lemma_c')

const responses: Record<string, unknown> = {
  '/api/theorems/1/proofs': [proof(10, 1)],
  '/api/proofs/10/direct-dependencies': {
    axioms: [{ id: 7, name: 'ax_k' } as unknown as Axiom],
    lemmas: [
      { proof_id: 20, theorem: LEMMA_A },
      { proof_id: 30, theorem: LEMMA_B },
    ],
  } satisfies DirectDependencies,
  '/api/proofs/20/direct-dependencies': {
    axioms: [],
    // ROOT here would be a cycle; the ancestor guard must drop it.
    lemmas: [
      { proof_id: 10, theorem: ROOT },
      { proof_id: 40, theorem: LEMMA_C },
    ],
  } satisfies DirectDependencies,
}

let fetchMock: ReturnType<typeof vi.fn>

function requestedUrls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input))
}

beforeEach(() => {
  fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (!(url in responses)) throw new Error(`unexpected request: ${url}`)
    return Promise.resolve(
      new Response(JSON.stringify(responses[url]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderGraph() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DependencyGraph theoremId={ROOT.id} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DependencyGraph', () => {
  it('shows direct lemmas from one bulk request and collapsed nodes fetch nothing', async () => {
    renderGraph()

    expect(await screen.findByText('lemma_a')).toBeTruthy()
    expect(screen.getByText('lemma_b')).toBeTruthy()
    expect(screen.getByText('公理 ax_k')).toBeTruthy()
    // Give any stray per-node queries a chance to fire before asserting.
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(requestedUrls()).toEqual(['/api/theorems/1/proofs', '/api/proofs/10/direct-dependencies'])
  })

  it('fetches a node’s dependencies only when it is expanded, keeping the cycle guard', async () => {
    renderGraph()
    await screen.findByText('lemma_a')

    await userEvent.click(screen.getByRole('button', { name: 'lemma_a の依存関係' }))

    expect(await screen.findByText('lemma_c')).toBeTruthy()
    expect(screen.queryByText('root_theorem')).toBeNull()
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(requestedUrls()).toEqual([
      '/api/theorems/1/proofs',
      '/api/proofs/10/direct-dependencies',
      '/api/proofs/20/direct-dependencies',
    ])
  })
})
