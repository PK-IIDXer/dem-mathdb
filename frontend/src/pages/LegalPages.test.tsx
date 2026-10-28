/// <reference types="node" />
// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import App from '../App'
import { LEGAL_ESTABLISHED_DATE } from './legalDate'

const approved = readFileSync('../docs/design/ux/public-legal-pages.md', 'utf8')
const pages = [
  { path: '/terms', ja: '利用規約', en: 'Terms of Use', section: 3 },
  { path: '/privacy', ja: 'プライバシーポリシー', en: 'Privacy Policy', section: 4 },
  { path: '/disclaimer', ja: '免責事項', en: 'Disclaimer', section: 5 },
]
// The approved copy is wrapped Markdown, so a line break between two Japanese characters is not a space.
const JA_GAP = /(?<=[^\x00-\x7F]) (?=[^\x00-\x7F])/g
const normalize = (text: string) => text.replace(/\s+/g, ' ').replace(JA_GAP, '').trim()

afterEach(cleanup)

it.each(pages)('renders $path with approved bilingual text, language and title', ({ path, ja, en, section }) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['config'], { read_only: true })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></QueryClientProvider>)

  const main = screen.getByRole('main')
  expect(within(main).getByRole('heading', { name: ja })).toBeTruthy()
  const english = within(main).getByRole('heading', { name: en }).closest('section')!
  expect(english.getAttribute('lang')).toBe('en')
  expect(within(english).getByRole('heading', { name: 'English' })).toBeTruthy()
  expect(main.querySelector('section')?.getAttribute('lang')).toBe('ja')
  expect(document.title).toBe(`${ja} — Deus Ex Machina`)

  const text = approved.split(`## ${section}. `)[1].split('\n## ')[0]
  const languages = text.split('### English')
  for (const [index, language] of ['ja', 'en'].entries()) {
    let expected = languages[index].split('\n').filter(line => line.startsWith('>'))
      .map(line => line.replace(/^> ?/, '').replace(/\*\*/g, '').replace(/^- /, '')).join(' ')
    if (!expected.includes('YYYY-MM-DD')) expected += index === 0 ? ' 制定日: YYYY-MM-DD' : ' Established: YYYY-MM-DD'
    expected = expected.replace('YYYY-MM-DD', LEGAL_ESTABLISHED_DATE)
    const actual = Array.from(main.querySelectorAll(`section[lang="${language}"] h2, section[lang="${language}"] h3, section[lang="${language}"] p, section[lang="${language}"] li`))
      .map(element => element.textContent).filter(value => value !== 'English').join(' ')
    expect(normalize(actual)).toBe(normalize(expected))
    expect(main.querySelector(`section[lang="${language}"]`)!.textContent).toContain('2026-10-29')
    expect(main.querySelector(`section[lang="${language}"]`)!.textContent).not.toContain('YYYY-MM-DD')

    if (language === 'ja') {
      // A stray space inside a Japanese sentence shows on screen, so the page itself must not have one.
      for (const element of main.querySelectorAll('section[lang="ja"] h2, section[lang="ja"] h3, section[lang="ja"] p, section[lang="ja"] li')) {
        expect(element.textContent?.match(JA_GAP) ?? []).toEqual([])
      }
    }
  }

  // Escapes keep the repository's legacy-reference scan focused on actual copy.
  expect(main.textContent).not.toMatch(/\u0041dSense|\u30a2フィリエイト|\u0061ffiliate|\u304a問い合わせ/i)
  expect(main.querySelector('a[href*="policies.google.com"]')).toBeNull()
  for (const [language, word] of [['ja', '\u5e83\u544a'], ['en', 'advertising']]) {
    const region = main.querySelector(`section[lang="${language}"]`)!
    const mentions = Array.from(region.querySelectorAll('h2, h3, p, li'))
      .filter(element => element.textContent?.includes(word))
    if (path === '/privacy') {
      const heading = within(region as HTMLElement).getByRole('heading', { name: /^3\. / })
      expect(mentions).toEqual([heading, heading.nextElementSibling])
      expect(region.textContent?.split(word).length).toBe(3)
    } else {
      expect(mentions).toEqual([])
    }
  }

  const footer = screen.getByRole('contentinfo')
  expect(within(footer).getAllByRole('link').map(link => [link.textContent?.trim(), link.getAttribute('href')])).toEqual([
    ['利用規約', '/terms'], ['プライバシーポリシー', '/privacy'],
    ['免責事項', '/disclaimer'], ['出典とライセンス', '/sources-licenses'],
  ])
})

it('uses the approved real enactment date', () => {
  expect(LEGAL_ESTABLISHED_DATE).not.toBe('YYYY-MM-DD')
  expect(LEGAL_ESTABLISHED_DATE).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  expect(new Date(LEGAL_ESTABLISHED_DATE + 'T00:00:00Z').toISOString().slice(0, 10)).toBe(LEGAL_ESTABLISHED_DATE)
  expect(LEGAL_ESTABLISHED_DATE).toBe('2026-10-29')
})
