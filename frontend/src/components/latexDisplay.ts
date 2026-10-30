import { t } from "../i18n/translate"
import katex from 'katex'

// Display-only limits, independent of formula registration and proof validation.
// Allow large formulas while bounding nesting, font switches and macro expansion.
export function renderDisplayLatex(source: string, display = false, beta = false): string | null {
  if (source.length > 32_768 || (source.match(/\\[A-Za-z]+/g)?.length ?? 0) > 2048 ||
      (source.match(/\\(?:tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)\b/g)?.length ?? 0) > 128 ||
      source.includes(t("model_180")) || /\\(?:href|url|includegraphics|htmlClass|htmlStyle|htmlId|htmlData)\b/.test(source)) return null
  let depth = 0
  for (let index = 0; index < source.length; index += 1) {
    if (source[index] === '\\') { index += 1; continue }
    if (source[index] === '{' && ++depth > 128) return null
    if (source[index] === '}') depth -= 1
  }
  try {
    const html = katex.renderToString(source, {
      throwOnError: false, displayMode: display, trust: false,
      strict: 'warn', maxSize: 10, maxExpand: 1000,
    })
    const parseError = html.startsWith('<span class="katex-error"')
    return parseError && (beta || html.includes('Too many expansions')) ? null : html
  } catch {
    return null
  }
}
