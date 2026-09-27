// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { useRef, useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { CommandPalette } from './CommandPalette'
import { CommandProvider, useCommand, useCommandApi } from './CommandProvider'

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function Harness({ unmountOrigin = false, onHome = () => undefined }: { unmountOrigin?: boolean; onHome?: () => void }) {
  const { execute } = useCommandApi()
  const [originVisible, setOriginVisible] = useState(true)
  useCommand('navigate.home', onHome)
  return (
    <>
      <div>{originVisible && <button type="button" onClick={() => {
          execute('palette.open')
          if (unmountOrigin) setOriginVisible(false)
        }}>external open</button>}</div>
      <main tabIndex={-1}><CommandPalette /></main>
    </>
  )
}

function FocusHarness({ onToggle }: { onToggle: () => void }) {
  const { execute } = useCommandApi()
  const planRef = useRef<HTMLDivElement>(null)
  const targetRef = useRef<HTMLButtonElement>(null)
  useCommand('plan.fill.premise', () => targetRef.current?.focus(), { scope: planRef })
  useCommand('formula.toggle-internals', onToggle)
  return (
    <main tabIndex={-1}>
      <div ref={planRef}>
        <button type="button" onClick={() => execute('palette.open')}>plan open</button>
        <button ref={targetRef} type="button">premise target</button>
      </div>
      <CommandPalette />
    </main>
  )
}

function ScopedCommitPaletteHarness({ run }: { run: (id: string) => void }) {
  const { execute } = useCommandApi()
  const outerRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  useCommand('step.commit', () => run('step.commit'), { scope: outerRef })
  useCommand('formula.commit', () => run('formula.commit'), { scope: innerRef })
  return (
    <main tabIndex={-1}>
      <div ref={outerRef}>
        <button type="button" onClick={() => execute('palette.open')}>outer open</button>
        <div ref={innerRef}>
          <button type="button" onClick={() => execute('palette.open')}>inner open</button>
        </div>
      </div>
      <CommandPalette />
    </main>
  )
}

function renderPalette(options: { unmountOrigin?: boolean; onHome?: () => void } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><CommandProvider><Harness {...options} /></CommandProvider></MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderFocusPalette(onToggle = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter><CommandProvider><FocusHarness onToggle={onToggle} /></CommandProvider></MemoryRouter>
    </QueryClientProvider>,
  )
  return onToggle
}

function renderScopedCommitPalette(run = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter><CommandProvider><ScopedCommitPaletteHarness run={run} /></CommandProvider></MemoryRouter>
    </QueryClientProvider>,
  )
  return run
}

function key(target: Element, init: KeyboardEventInit & { keyCode?: number }): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
  if (init.keyCode != null) Object.defineProperty(event, 'keyCode', { value: init.keyCode })
  target.dispatchEvent(event)
  return event
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('implements the dialog, combobox, listbox, active descendant, and focus return contract', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  renderPalette()
  const origin = screen.getByRole('button', { name: 'external open' })
  origin.focus()
  fireEvent.click(origin)

  const dialog = screen.getByRole('dialog', { name: '操作を検索' })
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  const listbox = screen.getByRole('listbox', { name: '候補' })
  expect(dialog.getAttribute('aria-modal')).toBe('true')
  expect(input.getAttribute('aria-controls')).toBe(listbox.id)
  expect(document.activeElement).toBe(input)

  const before = input.getAttribute('aria-activedescendant')
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  const after = input.getAttribute('aria-activedescendant')
  expect(after).not.toBe(before)
  expect(document.getElementById(after!)?.getAttribute('aria-selected')).toBe('true')

  fireEvent.keyDown(input, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(document.activeElement).toBe(origin)
})

it('searches entities only after two characters and uses formula search instead of listing formulas', async () => {
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url === '/api/formulas/search') return Promise.resolve(json({ items: [{ formula_id: 42, bindings: {} }], next_cursor: null }))
    return Promise.resolve(json([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  renderPalette()
  const user = userEvent.setup()
  await user.click(screen.getByText('操作を検索'))
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })

  await user.type(input, 'P')
  await new Promise((resolve) => setTimeout(resolve, 250))
  expect(fetchMock).not.toHaveBeenCalled()
  await user.type(input, '(')
  expect(await screen.findByText('Formula #42')).toBeTruthy()
  const urls = fetchMock.mock.calls.map(([value]) => String(value))
  expect(urls).toContain('/api/formulas/search')
  expect(urls).not.toContain('/api/formulas')
  expect(screen.getByText(/件$/).textContent).toMatch(/\d+ 件/)
})

it('executes only the active option once', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  const onHome = vi.fn()
  renderPalette({ onHome })
  const origin = screen.getByRole('button', { name: 'external open' })
  origin.focus()
  fireEvent.click(origin)
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: 'ホーム' } })
  fireEvent.keyDown(input, { key: 'Enter' })

  expect(onHome).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('main')))
})

it('preserves focus moved by a plan command and restores origin for a non-focus command', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  const onToggle = renderFocusPalette()
  const origin = screen.getByRole('button', { name: 'plan open' })
  origin.focus()
  fireEvent.click(origin)
  let input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: 'fill.premise' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'premise target' }))

  origin.focus()
  fireEvent.click(origin)
  input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: '内部表現を切替' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(onToggle).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(document.activeElement).toBe(origin)
})

it('resolves scoped commands from the focus held before the palette opened', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  const run = renderScopedCommitPalette()

  const outer = screen.getByRole('button', { name: 'outer open' })
  outer.focus()
  fireEvent.click(outer)
  let input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: 'step.commit' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(run).toHaveBeenLastCalledWith('step.commit')
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

  const inner = screen.getByRole('button', { name: 'inner open' })
  inner.focus()
  fireEvent.click(inner)
  input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: 'formula.commit' } })
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(run).toHaveBeenLastCalledWith('formula.commit')
  expect(run).toHaveBeenCalledTimes(2)
})

it.each(['isComposing', 'composition flag', 'keyCode 229'])('ignores palette navigation and execution during %s', (mode) => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  const onHome = vi.fn()
  renderPalette({ onHome })
  const origin = screen.getByRole('button', { name: 'external open' })
  origin.focus()
  fireEvent.click(origin)
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: 'ホーム' } })
  if (mode === 'composition flag') fireEvent.compositionStart(input)
  const extra = mode === 'isComposing' ? { isComposing: true } : mode === 'keyCode 229' ? { keyCode: 229 } : {}
  const activeId = input.getAttribute('aria-activedescendant')
  const events = ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].map((pressed) => key(input, { key: pressed, ...extra }))

  expect(input.getAttribute('aria-activedescendant')).toBe(activeId)
  expect(onHome).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: '操作を検索' })).toBeTruthy()
  expect(events.every((event) => !event.defaultPrevented)).toBe(true)
})

it('falls back to the palette trigger when the origin unmounts', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json([]))))
  renderPalette({ unmountOrigin: true })
  const origin = screen.getByRole('button', { name: 'external open' })
  origin.focus()
  fireEvent.click(origin)
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.keyDown(input, { key: 'Escape' })

  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: /操作を検索/ })))
})
