import { useSyncExternalStore } from 'react'
import { getLanguage, subscribeLanguage } from './language'

/** Works for pages rendered alone in tests and embedded viewers, too. */
export function useLanguage() {
  return useSyncExternalStore(subscribeLanguage, getLanguage, () => 'ja' as const)
}
