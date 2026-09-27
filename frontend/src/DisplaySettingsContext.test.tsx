// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CommandPalette } from './commands/CommandPalette'
import { CommandProvider } from './commands/CommandProvider'
import {
  DEFAULT_DISPLAY_SETTINGS,
  DISPLAY_SETTINGS_STORAGE_KEY,
  DisplaySettingsProvider,
  useDisplaySettings,
} from './DisplaySettingsContext'

function Harness() {
  const { density, internals } = useDisplaySettings()
  return (
    <>
      <output aria-label="density">{density}</output>
      <output aria-label="internals">{internals}</output>
      <CommandPalette />
    </>
  )
}

function renderSettings() {
  return render(
    <MemoryRouter>
      <CommandProvider>
        <DisplaySettingsProvider><Harness /></DisplaySettingsProvider>
      </CommandProvider>
    </MemoryRouter>,
  )
}

function runPaletteCommand(query: string) {
  fireEvent.click(screen.getByText('操作を検索'))
  const input = screen.getByRole('combobox', { name: 'コマンドまたは項目を検索' })
  fireEvent.change(input, { target: { value: query } })
  fireEvent.keyDown(input, { key: 'Enter' })
}

beforeEach(() => window.localStorage.clear())
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('DisplaySettingsProvider', () => {
  it('switches density and internals from the command palette and persists them', async () => {
    const first = renderSettings()
    expect(screen.getByLabelText('density').textContent).toBe('comfortable')
    expect(screen.getByLabelText('internals').textContent).toBe('off')

    runPaletteCommand('表示密度を切替')
    await waitFor(() => expect(screen.getByLabelText('density').textContent).toBe('compact'))
    runPaletteCommand('内部表示を切替')
    await waitFor(() => expect(screen.getByLabelText('internals').textContent).toBe('on'))
    await waitFor(() => expect(JSON.parse(
      window.localStorage.getItem(DISPLAY_SETTINGS_STORAGE_KEY) ?? '{}',
    )).toEqual({ density: 'compact', internals: 'on' }))

    first.unmount()
    renderSettings()
    expect(screen.getByLabelText('density').textContent).toBe('compact')
    expect(screen.getByLabelText('internals').textContent).toBe('on')
  })

  it('uses defaults for corrupt storage', () => {
    window.localStorage.setItem(DISPLAY_SETTINGS_STORAGE_KEY, '{broken')
    renderSettings()
    expect(screen.getByLabelText('density').textContent).toBe(DEFAULT_DISPLAY_SETTINGS.density)
    expect(screen.getByLabelText('internals').textContent).toBe(DEFAULT_DISPLAY_SETTINGS.internals)
  })

  it('uses defaults without throwing when storage cannot be read or written', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => renderSettings()).not.toThrow()
    expect(screen.getByLabelText('density').textContent).toBe('comfortable')
    expect(screen.getByLabelText('internals').textContent).toBe('off')
  })
})
