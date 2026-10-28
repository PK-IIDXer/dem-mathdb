// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { BetaContext } from '../components/BetaContext'
import { TermsPage } from './TermsPage'
import { PrivacyPolicyPage } from './PrivacyPolicyPage'
import { DisclaimerPage } from './DisclaimerPage'
import { BETA_LEGAL_ESTABLISHED_DATE } from './legalDate'

const document = readFileSync('../docs/design/ux/public-legal-pages.md', 'utf-8').replace(/\r\n/g, '\n').split('## 6. β 用')[1]
afterEach(cleanup)
it.each([['terms', TermsPage], ['privacy', PrivacyPolicyPage], ['disclaimer', DisclaimerPage]] as const)('matches the complete approved bilingual copy for %s', (kind, Page) => {
  const { container } = render(<MemoryRouter><BetaContext.Provider value={{ enabled: true, write_state: 'open', limits: {}, last_reset_at: null, next_reset_at: null, last_reset_error: null }}><Page /></BetaContext.Provider></MemoryRouter>)
  const approved = document.split(`### β ${kind}:`)[1].split('\n### β ')[0]
  for (const [language, heading] of [['ja', '日本語'], ['en', 'English']]) {
    const expected = approved.split(`#### ${heading}`)[1].split('\n#### ')[0].split('\n').filter(line => line.startsWith('> ')).map(line => line.slice(2).replace(/\*\*/g, '').replace('YYYY-MM-DD', BETA_LEGAL_ESTABLISHED_DATE)).join(' ')
    const actual = [...container.querySelectorAll(`section[lang="${language}"] h2, section[lang="${language}"] h3, section[lang="${language}"] p`)].map(node => node.textContent).join(' ')
    expect(actual).toBe(expected)
    const region = container.querySelector(`section[lang="${language}"]`)!
    expect(region.textContent).toContain('2026-10-29')
    expect(region.textContent).not.toContain('YYYY-MM-DD')

  }
  expect(container.textContent).not.toContain('下書き')
  expect(container.textContent).not.toContain('確認待ち')
  expect(screen.getByRole('link', { name: /Contact and removal/ }).getAttribute('href')).toBe('/contact')
  expect(BETA_LEGAL_ESTABLISHED_DATE).toBe('2026-10-29')
})

it('uses the approved real enactment date', () => {
  expect(BETA_LEGAL_ESTABLISHED_DATE).not.toBe('YYYY-MM-DD')
  expect(BETA_LEGAL_ESTABLISHED_DATE).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(new Date(BETA_LEGAL_ESTABLISHED_DATE + 'T00:00:00Z').toISOString().slice(0, 10)).toBe(BETA_LEGAL_ESTABLISHED_DATE)
  expect(BETA_LEGAL_ESTABLISHED_DATE).toBe('2026-10-29')
})
