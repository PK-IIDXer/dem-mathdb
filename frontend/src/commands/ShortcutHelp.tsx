import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useCommand, useCommandApi } from './CommandProvider'

export function ShortcutHelp() {
  const { inspect } = useCommandApi()
  const [open, setOpen] = useState(false)
  const originRef = useRef<HTMLElement | null>(null)
  const restoreFocusRef = useRef(false)
  const closeRef = useRef<HTMLButtonElement>(null)
  const headingId = useId()
  const show = useCallback(() => {
    originRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setOpen(true)
  }, [])
  const close = useCallback(() => {
    restoreFocusRef.current = true
    setOpen(false)
  }, [])
  useCommand('shortcuts.show', show)
  useCommand('palette.close', close, { enabled: open })

  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])

  useLayoutEffect(() => {
    if (open || !restoreFocusRef.current) return
    restoreFocusRef.current = false
    const origin = originRef.current
    if (origin && document.contains(origin)) origin.focus()
    else document.querySelector<HTMLElement>('[data-command-palette-trigger]')?.focus()
  }, [open])

  if (!open) return null
  const commands = inspect().filter(({ definition }) => definition.defaultBindings.length > 0 && definition.id !== 'palette.close')
  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-slate-950/40 px-4 pt-[15vh]">
      <div role="dialog" aria-modal="true" aria-labelledby={headingId} className="w-full max-w-lg rounded-xl bg-white p-4 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 id={headingId} className="font-semibold text-slate-900">キーボードショートカット</h2>
          <button ref={closeRef} type="button" onClick={close} className="rounded px-2 py-1 text-sm text-slate-500">閉じる Esc</button>
        </div>
        <dl className="mt-3 divide-y divide-slate-100 text-sm">
          {commands.map(({ definition, enabled }) => (
            <div key={definition.id} className={`flex justify-between gap-4 py-2 ${enabled ? '' : 'text-slate-400'}`}>
              <dt>{definition.label}</dt>
              <dd className="flex gap-1">{definition.defaultBindings.map((binding) => <kbd key={binding} className="rounded bg-slate-100 px-1.5 py-0.5">{binding}</kbd>)}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-xs text-slate-500">割り当てのない操作も「操作を検索」から実行できます。</p>
      </div>
    </div>
  )
}
