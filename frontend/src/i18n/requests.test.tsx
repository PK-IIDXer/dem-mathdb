// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../App'
import { createOnboardingFetch } from '../test/tutorialApi'
import { setupUser } from '../test/user'
import { ONBOARDING_FLOW_TIMEOUT } from '../test/timeouts'
import { setLanguage, type Language } from './language'
import { ContactPage } from '../pages/ContactPage'
import { BetaContext } from '../components/BetaContext'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

type RequestBytes = { method: string; url: string; body: string | null }
const beta = { enabled: true, write_state: 'open' as const, next_reset_at: null, last_reset_at: null, last_reset_error: null, limits: {} }
function record(name: string, data: unknown) {
  const directory = process.env.DEM_I18N_REPORT_DIR
  if (!directory) return
  mkdirSync(directory, { recursive: true })
  writeFileSync(path.join(directory, name + '.json'), JSON.stringify(data, null, 2) + '\n')
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

async function tutorial(language: Language) {
  setLanguage(language)
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  const base = createOnboardingFetch(true)
  const calls: RequestBytes[] = []
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ method: init?.method ?? 'GET', url: String(input), body: init?.body == null ? null : String(init.body) })
    return base(input, init)
  }))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const user = setupUser()
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/formulas?onboarding=1']}><App /></MemoryRouter></QueryClientProvider>)
  const ja = language === 'ja'
  let operations = 0
  const click = async (element: Element) => { operations++; await user.click(element) }
  const type = async (element: Element, text: string) => { operations++; await user.type(element, text) }
  await screen.findByText(ja ? '式を書いてみる' : 'Try writing a formula')
  await type(screen.getByPlaceholderText(ja ? '例: forall x. P(x) -> Q(x)' : 'Example: forall x. P(x) -> Q(x)'), 'forall x. P(x) -> P(x)')
  const section = screen.getByText(ja ? '論理式を登録' : 'Register a formula').closest('section')!
  const choose = await within(section).findByRole('button', { name: ja ? /この式を選ぶ|確認して登録する/ : /Select this formula|Review and register/ })
  await waitFor(() => expect((choose as HTMLButtonElement).disabled).toBe(false))
  await click(choose)
  await screen.findByText(ja ? '定理を宣言する' : 'Declare the theorem', {}, { timeout: 10_000 })
  await type(screen.getByLabelText('name'), 'my_first_theorem')
  await click(screen.getByRole('button', { name: ja ? '+ 変数' : '+ Variable' }))
  await click(screen.getByRole('button', { name: ja ? '登録' : 'Register' }))
  await click(await screen.findByText(ja ? '新規 Proof を作成' : 'Create a new Proof'))
  await click(await screen.findByText(ja ? '公理 K / S を検索して追加' : 'Search and add the required axioms'))
  await click(await screen.findByText(ja ? 'この MP を追加' : 'Add this MP'))
  await click(await screen.findByText(ja ? 'この MP を追加' : 'Add this MP'))
  await screen.findByText(ja ? '✓ 最初の verified theorem に到達しました。' : '✓ You have completed your first verified theorem.')
  await waitFor(() => expect(client.isFetching()).toBe(0))
  expect(operations).toBe(9)
  expect(base.mock.results.filter(result => result.type === 'throw')).toEqual([])
  cleanup()
  client.clear()
  return calls
}

it('sends identical request bytes for all nine tutorial operations, theorem registration and proof steps', async () => {
  const ja = await tutorial('ja')
  const en = await tutorial('en')
  // Preserve write order. Concurrent GET arrival order is irrelevant; preserve
  // their exact URL/query bytes and multiplicity without normalizing values.
  const writes = (calls: RequestBytes[]) => calls.filter(call => call.method !== 'GET')
  const reads = (calls: RequestBytes[]) => calls.filter(call => call.method === 'GET').map(call => JSON.stringify(call)).sort()
  expect(writes(en)).toEqual(writes(ja))
  expect(reads(en)).toEqual(reads(ja))
  expect(writes(en).some(call => call.url === '/api/theorems')).toBe(true)
  expect(writes(en).filter(call => /\/steps$/.test(call.url))).toHaveLength(6)
  record('tutorial-request-bytes', { ja, en, writesEqual: true, readBytesAndCountsEqual: true, operations: 9 })
}, ONBOARDING_FLOW_TIMEOUT * 2)

it('sends identical contact request bytes and retains input while changing languages', async () => {
  const requests: RequestBytes[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ method: init?.method ?? 'GET', url: String(input), body: String(init?.body) })
    return new Response('{}', { status: 201, headers: { 'Content-Type': 'application/json' } })
  }))
  for (const language of ['ja', 'en'] as const) {
    setLanguage(language)
    const user = setupUser()
    render(<MemoryRouter><BetaContext.Provider value={beta}><ContactPage /></BetaContext.Provider></MemoryRouter>)
    const ja = language === 'ja'
    await user.selectOptions(screen.getByLabelText(ja ? '種別' : 'Category'), 'removal')
    await user.type(screen.getByLabelText(ja ? '対象の頁のURL（任意・500文字まで）' : 'Page URL (optional, up to 500 characters)'), '/theorems/example?q=x')
    await user.type(screen.getByLabelText(ja ? '本文（必須・2,000文字まで）' : 'Message (required, up to 2,000 characters)'), '同じ本文 / same message')
    await user.type(screen.getByLabelText(ja ? '返信先（任意・254文字まで）' : 'Reply address (optional, up to 254 characters)'), 'reply@example.invalid')
    act(() => setLanguage(language === 'ja' ? 'en' : 'ja'))
    expect(screen.getByDisplayValue('同じ本文 / same message')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: ja ? 'Send' : '送信する' }))
    await screen.findByRole('status')
    cleanup()
  }
  expect(requests).toHaveLength(2)
  expect(requests[1]).toEqual(requests[0])
  expect(requests[0].method).toBe('POST')
  expect(requests[0].url).toBe('/api/contact')
  record('contact-request-bytes', { ja: requests[0], en: requests[1], equal: true })
})
