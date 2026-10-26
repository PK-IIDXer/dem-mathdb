// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ContactPage } from './ContactPage'
import { BetaContext } from '../components/BetaContext'
import type { BetaConfig } from '../api/config'
import App from '../App'

const beta: BetaConfig = { enabled: true, write_state: 'maintenance', last_reset_at: null, next_reset_at: null, last_reset_error: null, limits: {} }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
function show(enabled = true) {
  return render(<MemoryRouter><BetaContext.Provider value={enabled ? beta : null}><ContactPage /></BetaContext.Provider></MemoryRouter>)
}
function fetchResponse(status = 202, code?: string) {
  const fetcher = vi.fn(async () => ({ ok: status === 202, status, headers: new Headers({ 'Retry-After': '600' }), json: async () => code ? { code } : { status: 'accepted' } }))
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}
it('has no form outside beta', () => {
  const fetcher = fetchResponse()
  show(false)
  expect(screen.queryByRole('button', { name: '送信する' })).toBe(null)
  expect(fetcher).not.toHaveBeenCalled()
})
it('accepts a removal request during maintenance with optional reply address', async () => {
  const fetcher = fetchResponse()
  show()
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'removal' } })
  expect(screen.getByText(/対象の頁のURLを入力してください/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText(/対象の頁のURL/), { target: { value: '/theorems/example' } })
  fireEvent.change(screen.getByLabelText(/本文（必須/), { target: { value: '削除依頼です' } })
  fireEvent.click(screen.getByRole('button', { name: '送信する' }))
  expect(await screen.findByRole('status')).toHaveProperty('textContent', '受け付けました。個別の返信はお約束できません。')
  expect(fetcher).toHaveBeenCalledWith('/api/contact', expect.objectContaining({ method: 'POST', body: JSON.stringify({ kind: 'removal', target_url: '/theorems/example', message: '削除依頼です', reply_to: null }) }))
})
it.each([[429, 'beta.rate_limited', '600 秒'], [503, 'beta.contact_unavailable', '保存できません'], [422, 'beta.contact_invalid', '入力内容を確認']] as const)('explains %i failures without losing the message', async (status, code, expected) => {
  fetchResponse(status, code)
  show()
  fireEvent.change(screen.getByLabelText(/本文（必須/), { target: { value: 'please keep this text' } })
  fireEvent.click(screen.getByRole('button', { name: '送信する' }))
  expect((await screen.findByRole('alert')).textContent).toContain(expected)
  expect((screen.getByLabelText(/本文（必須/) as HTMLTextAreaElement).value).toBe('please keep this text')
})
it('enforces field lengths and URL prefix before sending', () => {
  const fetcher = fetchResponse()
  show()
  expect(screen.getByLabelText(/本文（必須/).getAttribute('maxlength')).toBe('2000')
  expect(screen.getByLabelText(/対象の頁のURL/).getAttribute('maxlength')).toBe('500')
  expect(screen.getByLabelText(/返信先（任意/).getAttribute('maxlength')).toBe('254')
  for (const [label, value] of [[/本文（必須/, 'x'.repeat(2001)], [/対象の頁のURL/, '/' + 'x'.repeat(500)], [/返信先（任意/, 'x'.repeat(255)], [/対象の頁のURL/, 'javascript:alert(1)']] as const) {
    for (const field of [/本文（必須/, /対象の頁のURL/, /返信先（任意/]) fireEvent.change(screen.getByLabelText(field), { target: { value: field.source === '本文（必須' ? 'ok' : '' } })
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
    fireEvent.submit(screen.getByRole('button', { name: '送信する' }).closest('form')!)
    expect(screen.getByRole('alert').textContent).toContain('入力内容を確認')
  }
  expect(fetcher).not.toHaveBeenCalled()
})
it('links to contact from both the beta banner and footer', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['config'], { read_only: false, beta })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/contact']}><App /></MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(within(screen.getByLabelText('匿名公開β')).getByRole('link', { name: 'お問い合わせ・削除依頼' }).getAttribute('href')).toBe('/contact'))
  expect(within(screen.getByRole('contentinfo')).getByRole('link', { name: 'お問い合わせ・削除依頼' }).getAttribute('href')).toBe('/contact')
})
