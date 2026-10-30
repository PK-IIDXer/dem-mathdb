import { useCallback, useState } from 'react'
import { useLanguage } from './useLanguage'

/** Retain the error and its parameters, so a language switch reformats it.
 * No input, request, query key or error code is rewritten. */
export function useDisplayError(): [string | null, (message: (() => string) | null) => void] {
  useLanguage()
  const [render, setRender] = useState<(() => string) | null>(null)
  const setError = useCallback((message: (() => string) | null) => { setRender(() => message) }, [])
  return [render?.() ?? null, setError]
}
