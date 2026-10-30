export type Language = 'ja' | 'en'
export const LANGUAGE_STORAGE_KEY = 'dem.language.v1'
const isLanguage = (value: unknown): value is Language => value === 'ja' || value === 'en'

/** Each source can be unavailable independently (privacy settings, SSR). */
export function resolveLanguage(): Language {
  try {
    const value = new URLSearchParams(window.location.search).get('lang')
    if (isLanguage(value)) {
      saveLanguage(value)
      return value
    }
  } catch { /* Try the next source. */ }
  try {
    const value = localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (isLanguage(value)) return value
  } catch { /* Storage is optional. */ }
  try {
    const value = navigator.languages?.[0]
    if (value) return value.toLowerCase().startsWith('ja') ? 'ja' : 'en'
  } catch { /* SSR and restricted browser environments. */ }
  return 'ja'
}

function saveLanguage(value: Language) {
  try { localStorage.setItem(LANGUAGE_STORAGE_KEY, value) } catch { /* Optional. */ }
}

let language: Language = resolveLanguage()
const listeners = new Set<() => void>()
export const getLanguage = (): Language => language
export function setLanguage(value: Language) {
  saveLanguage(value)
  if (typeof document !== 'undefined') document.documentElement.lang = value
  if (language === value) return
  language = value
  listeners.forEach(listener => listener())
}
export function subscribeLanguage(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export const locale = () => getLanguage() === 'ja' ? 'ja-JP' : 'en-US'
