// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Link } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { BetaContext } from './BetaContext'
import { BetaBanner } from './BetaBanner'
import { EntityBadge, SystemValidityNote, UserSymbolNotice } from './BetaIdentity'
import { entityOrigin, hasUserSymbols } from './betaIdentityModel'
import { BetaGettingStarted } from './BetaGettingStarted'
import { BetaWriteErrorNotice } from './BetaWriteErrorNotice'
import type { BetaConfig } from '../api/config'
import type { Symbol, Theorem } from '../api/types'
import { ApiError, api } from '../api/client'
import { HomePage } from '../pages/HomePage'

const beta: BetaConfig = { enabled: true, write_state: 'open', next_reset_at: '2026-11-02T04:00:00Z', last_reset_at: null, last_reset_error: null, limits: {} }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
function show(children: React.ReactNode, value: BetaConfig | null = beta, client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })) {
  client.setQueryData(['workspace', 'info'], { local_namespace_name: 'arbitrary-local' })
  return render(<QueryClientProvider client={client}><MemoryRouter><BetaContext.Provider value={value}>{children}</BetaContext.Provider></MemoryRouter></QueryClientProvider>)
}

it('shows no beta decorations outside beta and makes no extra network calls', () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  const { container } = show(<><BetaBanner /><EntityBadge namespace="arbitrary-local" detail /><SystemValidityNote /><UserSymbolNotice formulaIds={[99]} /><BetaGettingStarted theorems={[]} /></>, null)
  expect(container.textContent).toBe('')
  expect(fetcher).not.toHaveBeenCalled()
})

it.each(['maintenance', 'full'] as const)('shows local reset time, %s, and failed reset without claiming success', state => {
  show(<BetaBanner />, { ...beta, write_state: state, last_reset_error: { failed_at: '2026-10-22T01:02:03Z', stage: 'prepare' } })
  expect(screen.getByLabelText('匿名公開β').textContent).toContain(new Date(beta.next_reset_at!).toLocaleString('ja-JP'))
  expect(screen.getByText(/前回の定期リセットが完了しませんでした/)).toBeTruthy()
  expect(screen.getByText(state === 'full' ? /容量の上限/ : /メンテナンス中のため/)).toBeTruthy()
  expect(screen.getByText(/Public beta/)).toBeTruthy()
})

it('classifies arbitrary namespaces only by workspace equality, with no guessing before data arrives', () => {
  expect(entityOrigin('arbitrary-local', 'arbitrary-local')).toBe('user')
  expect(entityOrigin('another-foundation', 'arbitrary-local')).toBe('base')
  expect(entityOrigin(undefined, 'arbitrary-local')).toBe(null)
  const { container } = show(<><EntityBadge namespace="arbitrary-local" /><EntityBadge namespace="another-foundation" detail /><SystemValidityNote namespace="arbitrary-local" /></>)
  expect(container.textContent).toContain('利用者作成（誰でも編集できます）')
  expect(container.textContent).toContain('基本の内容は変更できません')
  expect(container.textContent).toContain('公理系に矛盾が無いことは示しません')
  expect(container.textContent).toContain('誰でも公理を追加・削除できます')
})

it('warns from symbol ownership in formula tokens, even when names look identical', async () => {
  const symbols = [{ id: 3, name: 'same', namespace_name: 'arbitrary-local' }, { id: 4, name: 'same', namespace_name: 'another-foundation' }] as Symbol[]
  expect(hasUserSymbols([{ symbol_id: 4 }], symbols, 'arbitrary-local')).toBe(false)
  expect(hasUserSymbols([{ symbol_id: 3 }], symbols, 'arbitrary-local')).toBe(true)
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['symbols'], symbols)
  client.setQueryData(['formulas', 9], { tokens: [{ symbol_id: 3 }] })
  show(<UserSymbolNotice formulaIds={[9]} />, beta, client)
  expect(await screen.findByText('利用者が作った記号を含みます')).toBeTruthy()
})

it('keeps an empty foundation navigable', () => {
  show(<BetaGettingStarted theorems={[]} />)
  expect(screen.getByText(/まだありません/)).toBeTruthy()
  expect(screen.getByRole('link', { name: /自分で定理を登録/ }).getAttribute('href')).toBe('/theorems')
})

it('offers the data-driven guide on an empty beta home without the foundation-specific legacy exercise', () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  for (const key of ['theorems', 'tags', 'axiomSystems']) client.setQueryData([key], [])
  client.setQueryData(['stats'], Object.fromEntries(['theorem_count', 'proven_theorem_count', 'proof_step_count', 'primitive_axiom_count', 'axiom_system_count', 'dependency_count'].map(key => [key, 0])))
  show(<HomePage />, beta, client)
  expect(screen.getByRole('region', { name: 'βの道案内' })).toBeTruthy()
  expect(screen.queryByText('はじめての定理')).toBe(null)
  expect(screen.getByRole('link', { name: /自分で定理を登録/ })).toBeTruthy()
})

it('selects an API-verified proof and links with public IDs rather than a seed name', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['theorems', 51, 'proofs'], [{ id: 70, public_id: 'proof-from-data', status: 'verified' }, { id: 71, status: 'draft' }])
  const theorem = { id: 51, public_id: 'theorem-from-data', name: 'Data-selected theorem', status: 'proven' } as Theorem
  show(<BetaGettingStarted theorems={[theorem]} />, beta, client)
  expect((await screen.findByRole('link', { name: /Data-selected theorem/ })).getAttribute('href')).toBe('/theorems/theorem-from-data/proofs/proof-from-data')
})

it('shows a failed write even when its form has no local onError renderer', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 429, headers: new Headers({ 'Retry-After': '17' }), json: async () => ({ code: 'beta.busy' }) })))
  show(<><BetaWriteErrorNotice /><Link to="/another">別の頁</Link><Link to="/">元の頁</Link></>)
  await expect(api.patch('/anything/description', {})).rejects.toBeInstanceOf(ApiError)
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('17 秒'))
  expect(screen.getByRole('alert').className).toContain('fixed')
  expect(screen.getByRole('alert').className).toContain('bottom-4')
  fireEvent.click(screen.getByRole('button', { name: '閉じる' }))
  expect(screen.queryByRole('alert')).toBe(null)
  await expect(api.patch('/anything/description', {})).rejects.toBeInstanceOf(ApiError)
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('link', { name: '別の頁' }))
  expect(screen.queryByRole('alert')).toBe(null)
  fireEvent.click(screen.getByRole('link', { name: '元の頁' }))
  expect(screen.queryByRole('alert')).toBe(null)
})
