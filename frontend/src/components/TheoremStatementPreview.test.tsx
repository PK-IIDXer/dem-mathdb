// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { HomePage } from '../pages/HomePage'
import { TheoremSearchPage } from '../pages/TheoremSearchPage'
import { InferenceRulePicker } from './InferenceRulePicker'
import { TheoremStatementPreview } from './TheoremStatementPreview'

const symbols = ['A', 'B', 'C', 'D'].map((name, index) => ({
  id: index + 1, name, arity: 0, notation_kind: 'prefix', symbol_type: { is_quantifier: false },
}))

function formula(id: number) {
  return { id, tokens: [{ position: 0, symbol_id: id, de_bruijn_index: null }] }
}

function theorem(id: number, premises: number[], conclusion: number, name = 'Implication chain') {
  return { id, public_id: 'theorem-' + id, name, status: 'proven', tags: [], external_checks: [],
    premise_formula_ids: premises, conclusion_formula_id: conclusion }
}

function latex(container: ParentNode) {
  return Array.from(container.querySelectorAll('annotation[encoding="application/x-tex"]'),
    (element) => element.textContent)
}

function show(view: ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={client}><MemoryRouter>{view}</MemoryRouter></QueryClientProvider>,
  )
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const threePremises = ['C', ',\\quad', 'A', ',\\quad', 'B', '\\;\\vdash\\;', 'D']
const cases: [number[], string[]][] = [
  [[], ['D']],
  [[2], ['B', '\\;\\vdash\\;', 'D']],
  [[3, 1, 2], threePremises],
]

it.each(cases)('renders premises %j in theorem order', (premises, expected) => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
  client.setQueryData(['symbols'], symbols)
  for (const { id } of symbols) client.setQueryData(['formulas', id], formula(id))

  const { container } = show(
    <TheoremStatementPreview theorem={theorem(1, premises, 4)} formulasWaiting={new Set()} />,
    client,
  )
  expect(latex(container)).toEqual(expected)
})

it.each([
  ['home', <HomePage />],
  ['search', <TheoremSearchPage />],
  ['rule picker', <InferenceRulePicker onChoose={() => {}} />],
] as const)('loads and renders statements in one batch on %s', async (_page, view) => {
  const fetcher = vi.fn(async (url: string) => {
    let body: unknown = []
    if (url.startsWith('/api/theorems')) {
      body = [theorem(1, [3, 1, 2], 4), theorem(2, [], 1, 'Second theorem')]
    } else if (url === '/api/symbols') {
      body = symbols
    } else if (url === '/api/formulas/batch?ids=1,2,3,4') {
      body = symbols.map(({ id }) => formula(id))
    } else if (url === '/api/stats') {
      return new Response(null, { status: 503 })
    }
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetcher)
  show(view)

  const row = (await screen.findByText('Implication chain')).closest('a, button')!
  await waitFor(() => expect(latex(row)).toEqual(threePremises))
  expect(fetcher.mock.calls.map(([url]) => url).filter((url) => url.startsWith('/api/formulas/')))
    .toEqual(['/api/formulas/batch?ids=1,2,3,4'])
  expect(fetcher.mock.calls.some(([url]) => url.endsWith('/premises'))).toBe(false)
})

