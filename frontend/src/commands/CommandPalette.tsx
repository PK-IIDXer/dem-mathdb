import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { axiomsApi } from '../api/axioms'
import { definitionsApi } from '../api/definitions'
import { formulasApi } from '../api/formulas'
import { proofsApi } from '../api/proofs'
import { symbolsApi } from '../api/symbols'
import { theoremsApi } from '../api/theorems'
import { isImeEvent, useCommand, useCommandApi } from './CommandProvider'

interface PaletteResult {
  id: string
  label: string
  group: string
  binding?: string
  disabledReason?: string
  focusAfterRun?: 'main'
  run: () => void
}

function matches(query: string, values: string[]): boolean {
  const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean)
  const haystack = values.join(' ').toLocaleLowerCase()
  return words.every((word) => haystack.includes(word))
}

function ignoreFailure<T>(promise: Promise<T[]>): Promise<T[]> {
  return promise.catch(() => [])
}

export function CommandPalette() {
  const navigate = useNavigate()
  const { execute, inspect } = useCommandApi()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const [entities, setEntities] = useState<PaletteResult[]>([])
  const [loading, setLoading] = useState(false)
  const originRef = useRef<HTMLElement | null>(null)
  const restoreFocusRef = useRef(false)
  const focusMainRef = useRef(false)
  const composingRef = useRef(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const headingId = useId()
  const listboxId = useId()

  const openPalette = useCallback(() => {
    originRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setOpen(true)
    setQuery('')
    setActiveIndex(0)
    focusMainRef.current = false
  }, [])
  const closePalette = useCallback(() => {
    restoreFocusRef.current = true
    focusMainRef.current = false
    setOpen(false)
  }, [])
  const runOpen = useCommand('palette.open', openPalette)
  useCommand('palette.close', closePalette, { enabled: open })

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useLayoutEffect(() => {
    if (open || !restoreFocusRef.current) return
    restoreFocusRef.current = false
    if (focusMainRef.current) {
      focusMainRef.current = false
      window.setTimeout(() => document.querySelector<HTMLElement>('main')?.focus(), 0)
      return
    }
    const target = originRef.current && document.contains(originRef.current)
      ? originRef.current
      : triggerRef.current && document.contains(triggerRef.current)
        ? triggerRef.current
        : document.querySelector<HTMLElement>('[data-command-palette-trigger]') ?? document.querySelector<HTMLElement>('main')
    target?.focus()
  }, [open])

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setEntities([])
      setLoading(false)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      const value = query.trim()
      const signal = controller.signal
      setLoading(true)
      const entityResults = async () => {
        const proofLookup = /^\d+$/.test(value) || /^[0-9a-f-]{8,}$/i.test(value)
          ? ignoreFailure(proofsApi.get(value, signal).then((proof) => [proof]))
          : Promise.resolve([])
        const [symbols, axioms, systems, theorems, definitions, formulas, proofs, rules] = await Promise.all([
          ignoreFailure(symbolsApi.listSymbols(undefined, false, signal)),
          ignoreFailure(axiomsApi.list({ search: value }, signal)),
          ignoreFailure(axiomsApi.listSystems(signal)),
          ignoreFailure(theoremsApi.list({ search: value }, signal)),
          ignoreFailure(definitionsApi.list({ search: value }, signal)),
          ignoreFailure(formulasApi.search(value, signal).then((result) => result.items)),
          proofLookup,
          ignoreFailure(theoremsApi.listRules(signal)),
        ])
        if (signal.aborted) return
        const entityResult = (id: string, label: string, group: string, path: string): PaletteResult => ({
          id,
          label,
          group,
          focusAfterRun: 'main',
          run: () => navigate(path),
        })
        const next: PaletteResult[] = [
          ...symbols.filter((item) => matches(value, [item.name, item.namespace_name])).slice(0, 10)
            .map((item) => entityResult(`symbol-${item.id}`, item.name, 'Symbols', `/symbols/${item.public_id}`)),
          ...axioms.slice(0, 10)
            .map((item) => entityResult(`axiom-${item.id}`, item.name, 'Axioms', `/axioms/${item.public_id}`)),
          ...systems.filter((item) => matches(value, [item.name])).slice(0, 10)
            .map((item) => entityResult(`axiom-system-${item.id}`, item.name, 'Axiom systems', `/axiom-systems/${item.id}`)),
          ...theorems.slice(0, 10)
            .map((item) => entityResult(`theorem-${item.id}`, item.name, 'Theorems', `/theorems/${item.public_id}`)),
          ...rules.filter((item) => document.querySelector('[data-rule-enabled="true"]') && matches(value, [item.name])).map((item): PaletteResult => ({
            id: `rule-${item.id}`,
            label: `推論定理: ${item.name}`,
            group: '推論定理',
            run: () => window.dispatchEvent(new CustomEvent('dem:choose-rule', {
              detail: { theoremId: item.id, mode: originRef.current?.closest('[data-top-down]') ? 'plan' : 'step' },
            })),
          })),
          ...definitions.slice(0, 10)
            .map((item) => entityResult(`definition-${item.id}`, item.name, 'Definitions', `/definitions/${item.public_id}`)),
          ...formulas.map((item) => entityResult(`formula-${item.formula_id}`, `Formula #${item.formula_id}`, 'Formulas', `/formulas?formula=${item.formula_id}`)),
          ...proofs.map((item) => entityResult(`proof-${item.id}`, `Proof #${item.id}`, 'Proofs', `/proofs/${item.public_id}`)),
        ]
        setEntities(next)
        setLoading(false)
      }
      void entityResults()
    }, 200)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [navigate, open, query])

  const commandResults = inspect(originRef.current)
    .filter(({ definition }) => definition.id !== 'palette.open' && definition.id !== 'palette.close')
    .filter(({ definition }) => matches(query, [definition.id, definition.label, ...definition.keywords]))
    .map(({ definition, enabled, disabledReason }): PaletteResult => ({
      id: `command-${definition.id}`,
      label: definition.label,
      group: definition.group,
      binding: definition.defaultBindings[0],
      disabledReason: enabled ? undefined : disabledReason,
      focusAfterRun: definition.group === 'navigation' ? 'main' : undefined,
      run: () => { execute(definition.id, { referenceElement: originRef.current }) },
    }))
  const results = useMemo(() => [...commandResults, ...entities], [commandResults, entities])
  const active = results[activeIndex]

  useEffect(() => {
    setActiveIndex(0)
  }, [query, entities])

  const choose = (result: PaletteResult) => {
    if (result.disabledReason) return
    result.run()
    const activeElement = document.activeElement
    const movedOutsidePalette = activeElement instanceof HTMLElement
      && activeElement !== document.body
      && !(dialogRef.current?.contains(activeElement) ?? false)
    restoreFocusRef.current = !movedOutsidePalette
    focusMainRef.current = result.focusAfterRun === 'main'
    setOpen(false)
  }

  return (
    <>
      <button
        ref={triggerRef}
        data-command-palette-trigger
        type="button"
        onClick={() => runOpen()}
        className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
      >
        操作を検索 <kbd aria-hidden="true">Ctrl/⌘ K</kbd>
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 px-4 pt-[12vh]"
          onMouseDown={(event) => { if (event.target === event.currentTarget) closePalette() }}
        >
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={headingId}
            className="w-full max-w-xl rounded-xl bg-white p-4 shadow-2xl"
            onKeyDown={(event) => {
              if (event.key !== 'Tab') return
              const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>('input, button:not(:disabled)')]
              if (focusable.length === 0) return
              const index = focusable.indexOf(document.activeElement as HTMLElement)
              const next = event.shiftKey ? (index <= 0 ? focusable.length - 1 : index - 1) : (index + 1) % focusable.length
              event.preventDefault()
              focusable[next].focus()
            }}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 id={headingId} className="font-semibold text-slate-900">操作を検索</h2>
              <button type="button" onClick={closePalette} aria-label="閉じる" className="rounded px-2 py-1 text-slate-500">Esc</button>
            </div>
            <input
              ref={inputRef}
              role="combobox"
              aria-label="コマンドまたは項目を検索"
              aria-expanded="true"
              aria-controls={listboxId}
              aria-autocomplete="list"
              aria-activedescendant={active ? `${listboxId}-${active.id}` : undefined}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onCompositionStart={() => { composingRef.current = true }}
              onCompositionEnd={() => { composingRef.current = false }}
              onKeyDown={(event) => {
                if (isImeEvent(event.nativeEvent, composingRef.current)) return
                if (event.key === 'ArrowDown') {
                  event.preventDefault()
                  setActiveIndex((index) => Math.min(index + 1, results.length - 1))
                } else if (event.key === 'ArrowUp') {
                  event.preventDefault()
                  setActiveIndex((index) => Math.max(index - 1, 0))
                } else if (event.key === 'Enter' && active) {
                  event.preventDefault()
                  choose(active)
                }
              }}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div id={listboxId} role="listbox" aria-label="候補" className="mt-2 max-h-80 overflow-y-auto">
              {results.map((result, index) => (
                <div
                  id={`${listboxId}-${result.id}`}
                  key={result.id}
                  role="option"
                  aria-selected={index === activeIndex}
                  aria-disabled={result.disabledReason ? 'true' : undefined}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(result)}
                  className={`flex cursor-pointer items-center justify-between rounded px-3 py-2 text-sm ${index === activeIndex ? 'bg-indigo-50 text-indigo-900' : 'text-slate-700'} ${result.disabledReason ? 'opacity-50' : ''}`}
                >
                  <span><span className="mr-2 text-xs text-slate-400">{result.group}</span>{result.label}</span>
                  {result.binding && <kbd className="text-xs text-slate-500">{result.binding}</kbd>}
                </div>
              ))}
            </div>
            <div aria-live="polite" className="mt-2 text-xs text-slate-500">
              {loading ? '検索中' : results.length === 0 ? '候補はありません' : `${results.length} 件`}
              {active?.disabledReason ? `。${active.disabledReason}` : ''}
            </div>
            <p className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-400">↑↓ 選択 / Enter 実行 / Esc 閉じる</p>
          </div>
        </div>
      )}
    </>
  )
}
