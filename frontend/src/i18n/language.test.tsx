// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { LanguageProvider, LanguageSwitch } from './LanguageContext'
import { getLanguage, LANGUAGE_STORAGE_KEY, resolveLanguage, setLanguage } from './language'
import { setupUser } from '../test/user'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  window.history.replaceState({}, '', '/')
})

it.each([
  ['?lang=ja', 'en', ['en-US'], 'ja'],
  ['?lang=en', 'ja', ['ja-JP'], 'en'],
  ['?lang=invalid', 'en', ['ja-JP'], 'en'],
  ['', 'broken', ['ja-JP', 'en-US'], 'ja'],
  ['', null, ['en-US', 'ja-JP'], 'en'],
  ['', null, ['fr-FR'], 'en'],
  ['', null, [], 'ja'],
] as const)('resolves URL=%s, storage=%s, browser=%j as %s', (query, saved, browser, expected) => {
  window.history.replaceState({}, '', '/' + query)
  localStorage.removeItem(LANGUAGE_STORAGE_KEY)
  if (saved != null) localStorage.setItem(LANGUAGE_STORAGE_KEY, saved)
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue([...browser])
  expect(resolveLanguage()).toBe(expected)
  if (query === '?lang=en' || query === '?lang=ja') expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe(expected)
})

it('continues after unavailable storage and navigator, and saves a URL choice when storage throws', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied') })
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['en-US'])
  expect(resolveLanguage()).toBe('en')
  vi.spyOn(navigator, 'languages', 'get').mockImplementation(() => { throw new Error('unavailable') })
  expect(resolveLanguage()).toBe('ja')
  window.history.replaceState({}, '', '/?lang=en')
  expect(resolveLanguage()).toBe('en')
})

it('switches with the keyboard, persists the choice and updates html lang', async () => {
  const user = setupUser()
  render(<LanguageProvider><LanguageSwitch /></LanguageProvider>)
  const english = screen.getByRole('button', { name: 'English' })
  english.focus()
  await user.keyboard(' ')
  expect(getLanguage()).toBe('en')
  expect(document.documentElement.lang).toBe('en')
  expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en')
  expect(english.getAttribute('aria-pressed')).toBe('true')
  act(() => setLanguage('ja'))
  expect(document.documentElement.lang).toBe('ja')
  expect(screen.getByRole('button', { name: '日本語' }).getAttribute('aria-pressed')).toBe('true')
})
