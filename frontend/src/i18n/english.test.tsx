// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from '../App'
import { errorGuidance } from '../api/errorGuidance'
import { ApiError } from '../api/client'
import { BetaContext } from '../components/BetaContext'
import { BetaBanner } from '../components/BetaBanner'
import { ContactPage } from '../pages/ContactPage'
import { TermsPage } from '../pages/TermsPage'
import { PrivacyPolicyPage } from '../pages/PrivacyPolicyPage'
import { DisclaimerPage } from '../pages/DisclaimerPage'
import { createOnboardingFetch } from '../test/tutorialApi'
import { setupUser } from '../test/user'
import fixture from '../test/fixtures/i18n-tutorial.json'
import { setLanguage } from './language'
import { COMMAND_BY_ID } from '../commands/commands'
import { CommandProvider } from '../commands/CommandProvider'
import { CommandPalette } from '../commands/CommandPalette'

const beta = { enabled: true, write_state: 'open' as const, next_reset_at: null, last_reset_at: null, last_reset_error: null, limits: {} }
beforeEach(() => setLanguage('en'))
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it.each([
  ['/', 'Recent theorems'], ['/theorems', 'Register a theorem'],
  [`/theorems/${fixture.onboarding.theorem.public_id}`, '← Back to search'],
  [`/proofs/${fixture.onboarding.proof.public_id}`, 'Proof goal'],
])('shows English on %s while preserving database names', async (route, text) => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  const base = createOnboardingFetch(true)
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/stats') return Promise.resolve(new Response(JSON.stringify({ theorem_count: 1234, proven_theorem_count: 1, proof_step_count: 1, primitive_axiom_count: 1, axiom_system_count: 1, dependency_count: 1 })))
    if (url === `/api/proofs/${fixture.onboarding.proof.public_id}`) return Promise.resolve(new Response(JSON.stringify(fixture.onboarding.proof)))
    if (route.startsWith('/proofs/') && url === `/api/theorems/${fixture.onboarding.theorem.id}/proofs`) return Promise.resolve(new Response(JSON.stringify([fixture.onboarding.proof])))
    return base(input, init)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>)
  await screen.findByText(text, { exact: false })
  expect(screen.getByRole('link', { name: 'Home' })).toBeTruthy()
  expect(screen.getByRole('complementary', { name: 'Anonymous public beta' })).toBeTruthy()
  expect(document.documentElement.lang).toBe('en')
  if (route === '/') expect(await screen.findByText('1,234')).toBeTruthy()
  if (route.startsWith('/theorems')) expect(await screen.findByText(fixture.onboarding.theorem.name, { exact: false })).toBeTruthy()
  await waitFor(() => expect(client.isFetching()).toBe(0))
})

it.each([
  [429, 'beta.rate_limited', 'Please wait about 11 seconds'],
  [503, 'beta.maintenance', 'Writes are paused for maintenance'],
  [409, 'beta.full', 'until the next reset'],
  [403, 'beta.disabled', 'unavailable in the beta'],
  [400, 'formula.too_deep', 'nested too deeply'],
  [503, null, 'Under maintenance'],
] as const)('shows English guidance for %s/%s', (status, code, expected) => {
  expect(errorGuidance(status, code ? { code } : null, 11)).toContain(expected)
})

it('formats embedded limits and changes an existing API error with the language', () => {
  expect(errorGuidance(429, { code: 'beta.rate_limited' }, 1)).toContain('1 second and')
  expect(errorGuidance(400, { code: 'beta.limit_exceeded', limit: 'proof_steps', maximum: 99 }, null)).toBe('The limit for Proof steps (maximum 99) has been exceeded. Reduce the input and try again.')
  const error = new ApiError(503, { code: 'beta.maintenance' })
  expect(error.message).toContain('Writes are paused')
  setLanguage('ja')
  expect(error.message).toContain('メンテナンス中')
})

it.each(['maintenance', 'full'] as const)('shows the English %s banner', state => {
  render(<MemoryRouter><BetaContext.Provider value={{ ...beta, write_state: state }}><BetaBanner /></BetaContext.Provider></MemoryRouter>)
  expect(screen.getByText(state === 'full' ? /Capacity has been reached/ : /Writes are paused/)).toBeTruthy()
  expect(document.body.textContent).not.toMatch(/[ぁ-んァ-ヶ一-龯]/u)
})

it.each([TermsPage, PrivacyPolicyPage, DisclaimerPage])('shows only English legal copy, dates and the reference notice', Page => {
  for (const config of [null, beta]) {
    const { container } = render(<MemoryRouter><BetaContext.Provider value={config}><Page /></BetaContext.Provider></MemoryRouter>)
    expect(screen.getByText(/Japanese text is authoritative/)).toBeTruthy()
    expect(container.querySelector('section[lang="ja"]')).toBeNull()
    expect(container.textContent).toContain('2026-10-29')
    expect(container.textContent).not.toMatch(/[ぁ-んァ-ヶ一-龯]/u)
    cleanup()
  }
})

it('shows English contact consent and switches commands without changing their identity', async () => {
  const command = COMMAND_BY_ID.get('open.theorem')!
  expect(command.label).toBe('Open theorem')
  const user = setupUser()
  render(<MemoryRouter><BetaContext.Provider value={beta}><ContactPage /></BetaContext.Provider></MemoryRouter>)
  expect(screen.getByText(/message is sent to Slack/)).toBeTruthy()
  await user.type(screen.getByLabelText('Message (required, up to 2,000 characters)'), 'unsent input')
  act(() => setLanguage('ja'))
  expect(COMMAND_BY_ID.get('open.theorem')).toBe(command)
  expect(command.label).toBe('theoremを開く')
  expect(screen.getByDisplayValue('unsent input')).toBeTruthy()
  expect(screen.getByRole('button', { name: '送信する' })).toBeTruthy()
})

it.each([429, 503])('shows a %s write error and reformats it when switching language without resubmitting', async status => {
  const fetcher = vi.fn(async () => new Response(JSON.stringify({ code: status === 429 ? 'beta.rate_limited' : 'beta.maintenance' }), { status, headers: { 'Content-Type': 'application/json', 'Retry-After': '11' } }))
  vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter><BetaContext.Provider value={beta}><ContactPage /></BetaContext.Provider></MemoryRouter>)
  const user = setupUser()
  await user.type(screen.getByLabelText('Message (required, up to 2,000 characters)'), 'unchanged message')
  await user.click(screen.getByRole('button', { name: 'Send' }))
  const error = await screen.findByRole('alert')
  expect(error.textContent).toContain(status === 429 ? '11 seconds' : 'maintenance')
  act(() => setLanguage('ja'))
  expect(error.textContent).toContain(status === 429 ? '11 秒' : 'メンテナンス')
  expect(screen.getByDisplayValue('unchanged message')).toBeTruthy()
  expect(fetcher).toHaveBeenCalledTimes(1)
})

it('searches command labels in English and retains existing Japanese keywords', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => new Response(String(input).includes('/formulas/search') ? '{"items":[]}' : '[]', { headers: { 'Content-Type': 'application/json' } })))
  render(<MemoryRouter><CommandProvider><CommandPalette /></CommandProvider></MemoryRouter>)
  const user = setupUser()
  await user.click(screen.getByRole('button', { name: /Search actions/ }))
  const input = screen.getByRole('combobox', { name: 'Search commands or items' })
  await user.type(input, 'Go to Home')
  expect(await screen.findByRole('option', { name: /Go to Home/ })).toBeTruthy()
  await user.clear(input)
  await user.type(input, '推論定理')
  expect(await screen.findByRole('option', { name: /Use inference theorem/ })).toBeTruthy()
})
