import { useEffect, useState } from 'react'

/** Returns `value` once it has stopped changing for `delayMs`. The first render
 * returns `value` as-is, so an initial state (e.g. read from the URL) is used
 * without waiting. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}
