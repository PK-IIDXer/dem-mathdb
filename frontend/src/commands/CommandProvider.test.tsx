// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { COMMANDS } from './commands'
import { CommandProvider, useCommand } from './CommandProvider'

function Harness({ run }: { run: () => void | Promise<void> }) {
  const execute = useCommand('palette.open', run)
  return (
    <div>
      <input aria-label="editable" />
      <button type="button" onClick={() => execute()}>open</button>
    </div>
  )
}

function AllShortcutsHarness({ run }: { run: (id: string) => void | Promise<void> }) {
  const editorRef = useRef<HTMLDivElement>(null)
  useCommand('palette.open', () => run('palette.open'))
  useCommand('formula.symbols', () => run('formula.symbols'), { scope: editorRef })
  useCommand('formula.commit', () => run('formula.commit'), { scope: editorRef })
  useCommand('shortcuts.show', () => run('shortcuts.show'))
  useCommand('search.focus', () => run('search.focus'))
  useCommand('navigate.home', () => run('navigate.home'))
  useCommand('proof.view.tree', () => run('proof.view.tree'))
  return <div ref={editorRef}><input aria-label="all editable" /></div>
}

function NestedCommitHarness({ run }: { run: (id: string) => void }) {
  const outerRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  useCommand('step.commit', () => run('step.commit'), { scope: outerRef })
  useCommand('formula.commit', () => run('formula.commit'), { scope: innerRef })
  return (
    <div ref={outerRef}>
      <input aria-label="outer field" />
      <div ref={innerRef}><input aria-label="inner editor" /></div>
    </div>
  )
}

function renderAllShortcuts(run: (id: string) => void | Promise<void> = vi.fn(), route = '/') {
  render(<MemoryRouter initialEntries={[route]}><CommandProvider><AllShortcutsHarness run={run} /></CommandProvider></MemoryRouter>)
  return run
}

function renderHarness(run = vi.fn()) {
  render(
    <MemoryRouter>
      <CommandProvider><Harness run={run} /></CommandProvider>
    </MemoryRouter>,
  )
  return run
}

function key(target: Element, init: KeyboardEventInit & { keyCode?: number }): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
  if (init.keyCode != null) Object.defineProperty(event, 'keyCode', { value: init.keyCode })
  target.dispatchEvent(event)
  return event
}

afterEach(cleanup)

describe('command registry', () => {
  it('has unique stable ids and no binding collision inside one declared scope', () => {
    expect(new Set(COMMANDS.map((command) => command.id)).size).toBe(COMMANDS.length)
    const bindings = new Set<string>()
    for (const command of COMMANDS) {
      for (const binding of command.defaultBindings) {
        const key = `${command.bindingScope ?? 'global'}:${binding}`
        expect(bindings.has(key), key).toBe(false)
        bindings.add(key)
      }
    }
    expect(COMMANDS.find((command) => command.id === 'step.command-line.open')?.implemented).toBe(false)
  })

  it('excludes mutation commands in read-only mode', () => {
    const visible = new Set(COMMANDS
      .filter((command) => command.implemented !== false && command.when({ pathname: '/theorems', readOnly: true }))
      .map((command) => command.id))
    for (const id of ['formula.commit', 'theorem.commit', 'theorem.variable.add', 'step.commit', 'plan.assume', 'symbol.create']) {
      expect(visible.has(id), id).toBe(false)
    }
  })
})

describe('shortcut dispatcher', () => {
  it('routes the button and both palette bindings through one executor', () => {
    const run = renderHarness()
    fireEvent.click(screen.getByRole('button', { name: 'open' }))
    const first = key(document.body, { key: 'k', ctrlKey: true })
    const second = key(document.body, { key: '.', ctrlKey: true })
    expect(run).toHaveBeenCalledTimes(3)
    expect(first.defaultPrevented).toBe(true)
    expect(second.defaultPrevented).toBe(true)
  })

  it.each([
    ['isComposing', (input: HTMLInputElement) => key(input, { key: 'k', ctrlKey: true, isComposing: true })],
    ['composition flag', (input: HTMLInputElement) => {
      fireEvent.compositionStart(input)
      return key(input, { key: 'k', ctrlKey: true })
    }],
    ['keyCode 229', (input: HTMLInputElement) => key(input, { key: 'k', ctrlKey: true, keyCode: 229 })],
  ])('ignores %s without preventing the native event', (_name, dispatch) => {
    const run = renderHarness()
    const event = dispatch(screen.getByRole('textbox', { name: 'editable' }))
    expect(run).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('does not take unmodified text in an editable and ignores repeat', () => {
    const run = renderHarness()
    const input = screen.getByRole('textbox', { name: 'editable' })
    for (const character of ['?', '/', 'g', 'v']) {
      const event = key(input, { key: character })
      expect(event.defaultPrevented).toBe(false)
    }
    const repeated = key(input, { key: 'k', ctrlKey: true, repeat: true })
    expect(repeated.defaultPrevented).toBe(false)
    expect(run).not.toHaveBeenCalled()
  })

  it('resolves Mod+Enter to the nearest scoped owner and never falls back outside a scope', () => {
    const run = vi.fn()
    render(<MemoryRouter><CommandProvider><NestedCommitHarness run={run} /></CommandProvider></MemoryRouter>)

    const outer = screen.getByRole('textbox', { name: 'outer field' })
    outer.focus()
    const outerEvent = key(outer, { key: 'Enter', ctrlKey: true })
    expect(run).toHaveBeenLastCalledWith('step.commit')
    expect(outerEvent.defaultPrevented).toBe(true)

    const inner = screen.getByRole('textbox', { name: 'inner editor' })
    inner.focus()
    const innerEvent = key(inner, { key: 'Enter', ctrlKey: true })
    expect(run).toHaveBeenLastCalledWith('formula.commit')
    expect(innerEvent.defaultPrevented).toBe(true)

    inner.blur()
    expect(document.activeElement).toBe(document.body)
    const bodyEvent = key(document.body, { key: 'Enter', ctrlKey: true })
    expect(run).toHaveBeenCalledTimes(2)
    expect(bodyEvent.defaultPrevented).toBe(false)
  })

  it('dispatches page-only help, search, navigation, and view sequences', () => {
    const run = renderAllShortcuts(vi.fn(), '/search') as ReturnType<typeof vi.fn>
    key(document.body, { key: '?', shiftKey: true })
    key(document.body, { key: '/' })
    key(document.body, { key: 'g' })
    key(document.body, { key: 'h' })
    expect(run.mock.calls.map(([id]) => id)).toEqual([
      'shortcuts.show', 'search.focus', 'navigate.home',
    ])

    cleanup()
    const proofRun = renderAllShortcuts(vi.fn(), '/proofs/1') as ReturnType<typeof vi.fn>
    key(document.body, { key: 'v' })
    key(document.body, { key: 't' })
    expect(proofRun).toHaveBeenCalledWith('proof.view.tree')
  })

  it.each(['/search', '/axioms', '/theorems', '/definitions'])('enables search focus on list page %s', (route) => {
    const run = renderAllShortcuts(vi.fn(), route) as ReturnType<typeof vi.fn>
    const event = key(document.body, { key: '/' })
    expect(run).toHaveBeenCalledWith('search.focus')
    expect(event.defaultPrevented).toBe(true)
  })

  it.each([
    ['k', 'palette.open'], ['.', 'palette.open'], ['Enter', 'formula.commit'], ['/', 'formula.symbols'],
  ])('does not treat Ctrl+Shift+%s as %s', (pressed, _id) => {
    const run = renderAllShortcuts() as ReturnType<typeof vi.fn>
    const input = screen.getByRole('textbox', { name: 'all editable' })
    input.focus()
    const event = key(input, { key: pressed, ctrlKey: true, shiftKey: true })
    expect(run).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it.each(['isComposing', 'composition flag', 'keyCode 229'])('blocks every shortcut family during %s', (mode) => {
    const run = renderAllShortcuts()
    const input = screen.getByRole('textbox', { name: 'all editable' })
    if (mode === 'composition flag') fireEvent.compositionStart(input)
    const extra = mode === 'isComposing' ? { isComposing: true } : mode === 'keyCode 229' ? { keyCode: 229 } : {}
    const events = [
      key(input, { key: 'k', ctrlKey: true, ...extra }),
      key(input, { key: '/', ctrlKey: true, ...extra }),
      key(input, { key: 'Enter', ctrlKey: true, ...extra }),
      key(input, { key: '?', shiftKey: true, ...extra }),
      key(input, { key: '/', ...extra }),
      key(input, { key: 'g', ...extra }),
      key(input, { key: 'h', ...extra }),
    ]
    expect(run).not.toHaveBeenCalled()
    expect(events.every((event) => !event.defaultPrevented)).toBe(true)
  })

  it('suppresses repeated and pending mutation shortcuts', async () => {
    let release!: () => void
    const pending = new Promise<void>((resolve) => { release = resolve })
    const run = vi.fn(() => pending)
    renderAllShortcuts((id) => id === 'formula.commit' ? run() : undefined)
    const input = screen.getByRole('textbox', { name: 'all editable' })
    input.focus()
    const first = key(input, { key: 'Enter', ctrlKey: true })
    const second = key(input, { key: 'Enter', ctrlKey: true })
    const repeated = key(input, { key: 'Enter', ctrlKey: true, repeat: true })
    expect(run).toHaveBeenCalledTimes(1)
    expect(first.defaultPrevented).toBe(true)
    expect(second.defaultPrevented).toBe(false)
    expect(repeated.defaultPrevented).toBe(false)
    release()
    await pending
  })
})
