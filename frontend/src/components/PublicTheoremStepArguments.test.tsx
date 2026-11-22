// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import type { ProofStep } from '../api/types'
import { setLanguage } from '../i18n/language'
import fixture from '../test/fixtures/public-theorem-step-arguments.json'
import { symbols } from '../test/fixtures/public-zfc-mk.json'
import { setupUser } from '../test/user'
import { StepForm } from './StepForm/StepForm'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it.each([false, true])('submits steps in premise order (exact second premise candidate: %s)', async (exactSecondCandidate) => {
  setLanguage('en')
  const { lemma, steps, suggestion } = fixture
  const proofId = steps[0].proof_id
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['theorems', lemma.id, 'premises'], [])
  client.setQueryData(['theorems', 'lemma-picker'], [lemma])
  client.setQueryData(['axioms'], [])
  client.setQueryData(['symbols'], symbols)
  const submit = vi.fn()
  const suggest = vi.fn()
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  })
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path.startsWith('/api/theorems/applicable?')) {
      return json([{ theorem: lemma, is_schematic: true, score: 1 }])
    }
    if (path === `/api/proofs/${proofId}/steps/suggest`) {
      suggest(JSON.parse(String(init?.body)))
      return json(exactSecondCandidate
        ? suggestion
        : { ...suggestion, arg_candidates: [suggestion.arg_candidates[0], []] })
    }
    if (path === `/api/proofs/${proofId}/steps`) {
      submit(JSON.parse(String(init?.body)))
      return json(steps[0], 201)
    }
    throw new Error(`Unexpected request: ${path}`)
  })
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <StepForm proofId={proofId} theoremId={lemma.id} priorSteps={steps as ProofStep[]} onAdded={() => undefined} showRules={false} />
      </QueryClientProvider>
    </MemoryRouter>,
  )

  const user = setupUser()
  await user.click(screen.getByRole('button', { name: 'Use a lemma' }))
  await user.click(screen.getByRole('checkbox', { name: '#1' }))
  await user.click(screen.getByRole('checkbox', { name: '#0' }))
  await user.click(await screen.findByRole('button', { name: lemma.name }))
  expect(suggest).toHaveBeenCalledWith(expect.objectContaining({ arg_step_ords: [0, 1] }))
  const first = await screen.findByRole<HTMLSelectElement>('combobox', { name: /Premises: 1/ })
  const second = screen.getByRole<HTMLSelectElement>('combobox', { name: /Premises: 2/ })
  expect([first.value, second.value]).toEqual(['1', '0'])
  await user.click(screen.getByRole('button', { name: 'Add this step' }))
  await waitFor(() => expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    kind: 'theorem',
    applied_proof_id: suggestion.applied_proof_id,
    arg_step_ords: [1, 0],
  })))
})
