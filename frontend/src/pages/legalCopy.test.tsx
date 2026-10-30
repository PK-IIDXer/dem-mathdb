// @vitest-environment jsdom
import { createHash } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { cleanup, render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import { BetaContext } from '../components/BetaContext'
import { setLanguage } from '../i18n/language'
import { TermsPage } from './TermsPage'
import { PrivacyPolicyPage } from './PrivacyPolicyPage'
import { DisclaimerPage } from './DisclaimerPage'

// Captured from the approved JSX before moving any text into LEGAL_COPY.
// Hashes cover every element's type, lang, class and exact text, plus title.
const expected: Record<string, string> = {
  "terms/standard/ja": "e782d0405345fd1530e7f826097c0a4c7b29c6fe2fd495676e11fd1d7df36151",
  "terms/standard/en": "1a4d1d6ad8c34445a8f619e74e42c3366a49fc8007e56be7a5f2729287224757",
  "terms/beta/ja": "7800fb935bee4dc927e6e5db7e3993002dee38866a442b9a865fc9f51b328d0f",
  "terms/beta/en": "f240bef98ac262b9ce7633722b210ca0a0c6bfed89ef7c95ee4e18ffbd56f1de",
  "privacy/standard/ja": "632da85994bf98e1e7a1cdf9ce375aacca5d7b379c35d704d99627590feeba7b",
  "privacy/standard/en": "f2984df6e924bbb816bf80e12ae20bd6f5426a449372c51ce7991aaa0bf93699",
  "privacy/beta/ja": "8e019e762851c04b76eb8c62ecda210b5226e77c0c1fbd5277c711626228bb24",
  "privacy/beta/en": "d26a2f1745904dff5f7c51eb8ba7b20b6404a5971cf82582230eeaff8e6151f7",
  "disclaimer/standard/ja": "702dc7e84babdfa86101d3f51448bef008240dfd5457c76b7f7cf6546e2192ab",
  "disclaimer/standard/en": "f544ac8a85995fae757dcf3683c38d05c3c32a2bf0371fdcff10a05cb38de333",
  "disclaimer/beta/ja": "d43841b3f9da91cc599a090f47acdb46d311b10aac53cd48d7ed3c63f0329b1c",
  "disclaimer/beta/en": "5981210740eb816bf86b3beda589fcde8f3c403a0cf541c6dd6b57533780c2c1"
}
const pages = [['terms', TermsPage], ['privacy', PrivacyPolicyPage], ['disclaimer', DisclaimerPage]] as const
const cases = pages.flatMap(([kind, Page]) => [false, true].flatMap(beta => (['ja', 'en'] as const).map(language => ({ kind, Page, beta, language }))))
afterEach(cleanup)
it.each(cases)('preserves approved elements and text: $kind beta=$beta language=$language', ({ kind, Page, beta, language }) => {
  setLanguage(language)
  const config = beta ? { enabled: true, write_state: 'open' as const, limits: {}, last_reset_at: null, next_reset_at: null, last_reset_error: null } : null
  const { container } = render(<MemoryRouter><BetaContext.Provider value={config}><Page /></BetaContext.Provider></MemoryRouter>)
  const elements = Array.from(container.querySelectorAll('*')).map(element => ({ tag: element.tagName, lang: element.getAttribute('lang'), className: element.getAttribute('class'), text: element.textContent }))
  const rendering = { title: document.title, elements }
  const sha256 = createHash('sha256').update(JSON.stringify(rendering)).digest('hex')
  expect(sha256).toBe(expected[`${kind}/${beta ? 'beta' : 'standard'}/${language}`])
  expect(Array.from(container.querySelectorAll('section')).map(section => section.lang)).toEqual(language === 'ja' ? ['ja', 'en'] : ['en'])
  const directory = process.env.DEM_I18N_REPORT_DIR
  if (directory) {
    mkdirSync(directory, { recursive: true })
    writeFileSync(path.join(directory, `legal-render-${kind}-${beta ? 'beta' : 'standard'}-${language}.json`), JSON.stringify({ rendering, sha256 }, null, 2) + '\n')
  }
})
