// @vitest-environment jsdom
import { cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { usePageTitle } from './usePageTitle'

afterEach(cleanup)

it('updates a loading title after data arrives and resets on leaving the page', () => {
  const { rerender, unmount } = renderHook(({ name }) => usePageTitle(name), { initialProps: { name: '定理' } })
  expect(document.title).toBe('定理 — Deus Ex Machina')
  rerender({ name: '例の定理' })
  expect(document.title).toBe('例の定理 — Deus Ex Machina')
  rerender({ name: '例の定理の証明' })
  expect(document.title).toBe('例の定理の証明 — Deus Ex Machina')
  unmount()
  expect(document.title).toBe('Deus Ex Machina')
})
