// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

afterEach(() => {
  cleanup()
})

// The shared setup skips pretty-printing the DOM only for the errors that
// waitFor/findBy* discard between retries.  These pin that every reported
// failure still carries the DOM.
describe('Testing Library failure messages', () => {
  it('keep the DOM dump, once, when a findBy query times out', async () => {
    render(<div><p>present-marker</p></div>)

    const error = await screen.findByText('absent', {}, { timeout: 200 }).catch((caught: Error) => caught)

    expect(error).toBeInstanceOf(Error)
    expect((error as Error).name).toBe('TestingLibraryElementError')
    expect((error as Error).message).toContain('Unable to find an element with the text: absent')
    expect((error as Error).message.split('present-marker')).toHaveLength(2)
    expect((error as Error).stack).toContain('setup.test.tsx')
  })

  it('keep the DOM dump when a getBy query inside waitFor times out', async () => {
    render(<div><p>present-marker</p></div>)

    const error = await waitFor(() => screen.getByRole('button', { name: 'absent' }), { timeout: 200 })
      .catch((caught: Error) => caught)

    expect((error as Error).message).toMatch(/Unable to find .*button.*absent/)
    expect((error as Error).message).toContain('present-marker')
  })

  it('keep the DOM dump when a getBy query fails outside waitFor', () => {
    render(<div><p>present-marker</p></div>)

    expect(() => screen.getByText('absent')).toThrow(/present-marker/)
  })
})
