/* oxlint-disable react/only-export-components -- provider hooks and keyboard predicates share one command runtime */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { useLocation } from 'react-router-dom'
import { useReadOnly } from '../ReadOnlyContext'
import { COMMAND_BY_ID, COMMANDS, type CommandDefinition, type CommandEnvironment } from './commands'

interface Registration {
  enabled: () => boolean
  execute: () => void | Promise<void>
  pending: boolean
  scope?: RefObject<HTMLElement | null>
}

interface CommandApi {
  environment: CommandEnvironment
  execute: (id: string, options?: { referenceElement?: Element | null }) => boolean
  executeRegistration: (id: string, token: symbol) => boolean
  available: () => CommandDefinition[]
  inspect: (referenceElement?: Element | null) => { definition: CommandDefinition; enabled: boolean; disabledReason?: string }[]
  register: (id: string, token: symbol, registration: Registration) => () => void
}

const CommandContext = createContext<CommandApi | null>(null)

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.matches('input, textarea, select, [contenteditable="true"], [contenteditable=""]')
}

export function isImeEvent(event: KeyboardEvent, composing: boolean): boolean {
  return composing || event.isComposing || event.keyCode === 229
}

export function eventBinding(event: KeyboardEvent): string | null {
  const modifier = event.ctrlKey || event.metaKey
  if (modifier && !event.altKey && !event.shiftKey) {
    if (event.key.toLowerCase() === 'k') return 'Mod+K'
    if (event.key === '.') return 'Mod+.'
    if (event.key === '/') return 'Mod+/'
    if (event.key === 'Enter') return 'Mod+Enter'
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) return event.key
  if (!event.ctrlKey && !event.metaKey && !event.altKey && event.shiftKey && event.key === '?') return '?'
  return null
}

export function CommandProvider({ children }: { children: ReactNode }) {
  const readOnly = useReadOnly()
  const { pathname } = useLocation()
  const environment = useMemo(() => ({ pathname, readOnly }), [pathname, readOnly])
  const environmentRef = useRef(environment)
  environmentRef.current = environment
  const registrations = useRef(new Map<string, Map<symbol, Registration>>())
  const [, setRegistrationVersion] = useState(0)
  const composing = useRef(false)
  const sequence = useRef<{ prefix: 'g' | 'v'; timer: number } | null>(null)

  const runRegistration = useCallback((registration: Registration): boolean => {
    if (registration.pending || !registration.enabled()) return false
    registration.pending = true
    try {
      const result = registration.execute()
      if (result instanceof Promise) {
        void result.finally(() => { registration.pending = false })
      } else {
        registration.pending = false
      }
    } catch (error) {
      registration.pending = false
      throw error
    }
    return true
  }, [])

  const register = useCallback((id: string, token: symbol, registration: Registration) => {
    const entries = registrations.current.get(id) ?? new Map<symbol, Registration>()
    entries.set(token, registration)
    registrations.current.set(id, entries)
    setRegistrationVersion((version) => version + 1)
    return () => {
      entries.delete(token)
      if (entries.size === 0) registrations.current.delete(id)
      setRegistrationVersion((version) => version + 1)
    }
  }, [])

  const eligibleRegistrations = useCallback((definition: CommandDefinition) => {
    if (definition.implemented === false || !definition.when(environmentRef.current)) return []
    return [...(registrations.current.get(definition.id)?.values() ?? [])]
      .filter((registration) => !registration.pending && registration.enabled())
  }, [])

  const scopedDistance = useCallback((registration: Registration, referenceElement: Element | null): number | undefined => {
    const scope = registration.scope?.current
    if (!scope || !referenceElement || !scope.contains(referenceElement)) return undefined
    let distance = 0
    let current: Node | null = referenceElement
    while (current && current !== scope) {
      current = current.parentNode
      distance += 1
    }
    return current === scope ? distance : undefined
  }, [])

  const resolveCommand = useCallback((definition: CommandDefinition, referenceElement: Element | null): Registration | undefined => {
    const eligible = eligibleRegistrations(definition)
    if (!definition.bindingScope) return eligible.length === 1 ? eligible[0] : undefined
    const scoped = eligible.flatMap((registration) => {
      const distance = scopedDistance(registration, referenceElement)
      return distance == null ? [] : [{ registration, distance }]
    })
    if (scoped.length === 0) return undefined
    const nearestDistance = Math.min(...scoped.map(({ distance }) => distance))
    const nearest = scoped.filter(({ distance }) => distance === nearestDistance)
    return nearest.length === 1 ? nearest[0].registration : undefined
  }, [eligibleRegistrations, scopedDistance])

  const resolveBinding = useCallback((binding: string, referenceElement: Element | null) => {
    const definitions = COMMANDS.filter((candidate) => candidate.defaultBindings.includes(binding))
    const scoped = definitions.flatMap((definition) => definition.bindingScope
      ? eligibleRegistrations(definition).flatMap((registration) => {
          const distance = scopedDistance(registration, referenceElement)
          return distance == null ? [] : [{ definition, registration, distance }]
        })
      : [])
    if (scoped.length > 0) {
      const nearestDistance = Math.min(...scoped.map(({ distance }) => distance))
      const nearest = scoped.filter(({ distance }) => distance === nearestDistance)
      return nearest.length === 1 ? nearest[0] : undefined
    }
    const unscoped = definitions.flatMap((definition) => definition.bindingScope
      ? []
      : eligibleRegistrations(definition).map((registration) => ({ definition, registration })))
    return unscoped.length === 1 ? unscoped[0] : undefined
  }, [eligibleRegistrations, scopedDistance])

  const execute = useCallback((id: string, options?: { referenceElement?: Element | null }): boolean => {
    const definition = COMMAND_BY_ID.get(id)
    if (!definition) return false
    const referenceElement = options && 'referenceElement' in options
      ? options.referenceElement ?? null
      : document.activeElement
    const registration = resolveCommand(definition, referenceElement)
    if (!registration) return false
    return runRegistration(registration)
  }, [resolveCommand, runRegistration])

  const executeRegistration = useCallback((id: string, token: symbol): boolean => {
    const definition = COMMAND_BY_ID.get(id)
    if (!definition || definition.implemented === false || !definition.when(environmentRef.current)) return false
    const registration = registrations.current.get(id)?.get(token)
    return registration ? runRegistration(registration) : false
  }, [runRegistration])

  const available = useCallback(
    () => COMMANDS.filter((command) => command.implemented !== false && command.when(environmentRef.current)),
    [],
  )
  const inspect = useCallback((referenceElement: Element | null = document.activeElement) => available().map((definition) => {
    const enabled = resolveCommand(definition, referenceElement) != null
    return { definition, enabled, disabledReason: enabled ? undefined : '現在の画面では利用できません' }
  }), [available, resolveCommand])

  useEffect(() => {
    const onCompositionStart = () => { composing.current = true }
    const onCompositionEnd = () => { composing.current = false }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.repeat || isImeEvent(event, composing.current)) return
      const binding = eventBinding(event)
      if (!binding) return
      const explicit = binding.startsWith('Mod+')
      if (!explicit && binding !== 'Escape' && isEditableTarget(event.target)) return
      if (sequence.current) {
        window.clearTimeout(sequence.current.timer)
        const chord = `${sequence.current.prefix} ${binding.toLocaleLowerCase()}`
        sequence.current = null
        if (binding === 'Escape') {
          event.preventDefault()
          return
        }
        const resolved = resolveBinding(chord, document.activeElement)
        const accepted = resolved ? runRegistration(resolved.registration) : false
        if (accepted) event.preventDefault()
        return
      }
      if (!explicit && (binding === 'g' || binding === 'v')) {
        sequence.current = {
          prefix: binding,
          timer: window.setTimeout(() => { sequence.current = null }, 1000),
        }
        event.preventDefault()
        return
      }
      const resolved = resolveBinding(binding, document.activeElement)
      const accepted = resolved ? runRegistration(resolved.registration) : false
      if (accepted) event.preventDefault()
    }
    document.addEventListener('compositionstart', onCompositionStart, true)
    document.addEventListener('compositionend', onCompositionEnd, true)
    document.addEventListener('keydown', onKeyDown)
    document.documentElement.dataset.commandKeyboardReady = 'true'
    return () => {
      document.removeEventListener('compositionstart', onCompositionStart, true)
      document.removeEventListener('compositionend', onCompositionEnd, true)
      document.removeEventListener('keydown', onKeyDown)
      delete document.documentElement.dataset.commandKeyboardReady
      if (sequence.current) window.clearTimeout(sequence.current.timer)
    }
  }, [resolveBinding, runRegistration])

  const api = useMemo(() => ({ environment, execute, executeRegistration, available, inspect, register }), [available, environment, execute, executeRegistration, inspect, register])
  return <CommandContext.Provider value={api}>{children}</CommandContext.Provider>
}

export function useCommand(
  id: string,
  handler: () => void | Promise<void>,
  options: { enabled?: boolean; scope?: RefObject<HTMLElement | null> } = {},
): () => boolean {
  const api = useContext(CommandContext)
  const token = useRef(Symbol(id))
  const handlerRef = useRef(handler)
  const enabledRef = useRef(options.enabled ?? true)
  const scopeRef = useRef(options.scope)
  handlerRef.current = handler
  enabledRef.current = options.enabled ?? true
  scopeRef.current = options.scope

  useEffect(() => api?.register(id, token.current, {
    enabled: () => enabledRef.current,
    execute: () => handlerRef.current(),
    get scope() { return scopeRef.current },
    pending: false,
  }), [api, id])

  return useCallback(() => {
    if (api) return api.executeRegistration(id, token.current)
    if (!(options.enabled ?? true)) return false
    void handlerRef.current()
    return true
  }, [api, id, options.enabled])
}

export function useCommandApi(): Pick<CommandApi, 'available' | 'inspect' | 'execute' | 'environment'> {
  const api = useContext(CommandContext)
  if (!api) throw new Error('useCommandApi must be used inside CommandProvider')
  return api
}
