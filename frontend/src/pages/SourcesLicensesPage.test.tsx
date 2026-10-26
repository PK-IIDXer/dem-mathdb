// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { theoremsApi } from '../api/theorems'
import { SourcesLicensesPage } from './SourcesLicensesPage'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('SourcesLicensesPage', () => {
  it('shows imported source counts, NOTICE status, and the full Apache license', async () => {
    vi.spyOn(theoremsApi, 'listExternalSources').mockResolvedValue([
      {
        library: 'mathlib',
        library_version: 'v4.33.1',
        library_commit: '0df444a360eaa60ab8c11dca51a86af692955474',
        license: 'Apache-2.0',
        imported_statements: 7,
        notice_status: 'absent',
      },
    ])
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SourcesLicensesPage />
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Mathlib v4.33.1')).toBeTruthy()
    expect(screen.getByText('7 文 ／ Apache-2.0')).toBeTruthy()
    expect(screen.getByText(/NOTICE: この版にはありません/)).toBeTruthy()
    const license = document.querySelector('pre')
    expect(license?.textContent).toContain('Apache License')
    expect(license?.textContent).toContain('Version 2.0, January 2004')
  })
})
