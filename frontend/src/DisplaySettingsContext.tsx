/* oxlint-disable react/only-export-components -- provider and hook share one persisted setting */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useCommand } from './commands/CommandProvider'

export type DisplayDensity = 'comfortable' | 'compact'
export type InternalsVisibility = 'off' | 'on'

interface DisplaySettings {
  density: DisplayDensity
  internals: InternalsVisibility
}

interface DisplaySettingsValue extends DisplaySettings {
  toggleDensity: () => void
  toggleInternals: () => void
}

export const DISPLAY_SETTINGS_STORAGE_KEY = 'dem.display-settings.v1'
export const DEFAULT_DISPLAY_SETTINGS: DisplaySettings = {
  density: 'comfortable',
  internals: 'off',
}

function readDisplaySettings(): DisplaySettings {
  try {
    const raw = window.localStorage.getItem(DISPLAY_SETTINGS_STORAGE_KEY)
    if (!raw) return DEFAULT_DISPLAY_SETTINGS
    const value = JSON.parse(raw) as Partial<DisplaySettings>
    if (
      (value.density === 'comfortable' || value.density === 'compact')
      && (value.internals === 'off' || value.internals === 'on')
    ) return { density: value.density, internals: value.internals }
  } catch {
    // Storage can be unavailable (for example, in privacy modes) or corrupt.
  }
  return DEFAULT_DISPLAY_SETTINGS
}

const DisplaySettingsContext = createContext<DisplaySettingsValue>({
  ...DEFAULT_DISPLAY_SETTINGS,
  toggleDensity: () => undefined,
  toggleInternals: () => undefined,
})

export function DisplaySettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(readDisplaySettings)
  const toggleDensity = () => setSettings((current) => ({
    ...current,
    density: current.density === 'comfortable' ? 'compact' : 'comfortable',
  }))
  const toggleInternals = () => setSettings((current) => ({
    ...current,
    internals: current.internals === 'off' ? 'on' : 'off',
  }))

  useCommand('display.density', toggleDensity)
  useCommand('display.internals', toggleInternals)

  useEffect(() => {
    try {
      window.localStorage.setItem(DISPLAY_SETTINGS_STORAGE_KEY, JSON.stringify(settings))
    } catch {
      // The UI remains usable with in-memory defaults when storage is blocked.
    }
  }, [settings])

  const value = useMemo(
    () => ({ ...settings, toggleDensity, toggleInternals }),
    [settings],
  )
  return <DisplaySettingsContext.Provider value={value}>{children}</DisplaySettingsContext.Provider>
}

export function useDisplaySettings(): DisplaySettingsValue {
  return useContext(DisplaySettingsContext)
}
