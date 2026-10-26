// @vitest-environment jsdom

import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Latex } from './Latex'

afterEach(() => {
  cleanup()
})

describe('Latex', () => {
  it('keeps the rendered markup when re-rendered with the same formula', () => {
    const { container, rerender } = render(<Latex>{'x \\to y'}</Latex>)
    const rendered = container.querySelector('.katex')
    expect(rendered).toBeTruthy()

    rerender(<Latex>{'x \\to y'}</Latex>)
    expect(container.querySelector('.katex')).toBe(rendered)

    rerender(<Latex>{'x \\to z'}</Latex>)
    expect(container.querySelector('.katex')).not.toBe(rendered)
    expect(container.querySelector('annotation')?.textContent).toBe('x \\to z')
  })
})
