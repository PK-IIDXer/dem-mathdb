// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import katex from 'katex'
import { Latex } from './Latex'
import { renderDisplayLatex } from './latexDisplay'
import { renderLatex, renderPreview, tokensToTree } from './FormulaEditor/model'
import { COMMON_READINGS, readTokens, printFormula } from './FormulaReading/reading'
import type { Symbol, Token } from '../api/types'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const type = { id: 2, name: 'logical', input_formula_type_id: 2, output_formula_type_id: 2, is_quantifier: false, fixed_arity: null, remarks: null, created_at: '' }
function symbol(id: number, name: string, arity: number, latex: string, kind?: 'not' | 'imp'): Symbol {
  return { id, public_id: [...COMMON_READINGS].find(([, value]) => value.kind === kind)?.[0] ?? 'test-atom', namespace_id: 13, namespace_name: 'different-foundation', name,
    arity, symbol_type: type, symbol_type_id: type.id, notation_kind: arity === 2 ? 'infix' : 'prefix', precedence: null, latex_template: latex, is_primitive: true, remarks: null, created_at: '' }
}
const symbols = new Map([symbol(1, '¬', 1, '\\neg', 'not'), symbol(2, '→', 2, '\\to', 'imp'), symbol(3, 'P', 0, 'P')].map(value => [value.id, value]))
const token = (id: number): Token => ({ symbol_id: id, de_bruijn_index: null })

it.each(['unary', 'right'] as const)('survives the accepted depth 992 %s formula in every display conversion', kind => {
  const tokens = kind === 'unary' ? [...Array.from({ length: 992 }, () => token(1)), token(3)]
    : [...Array.from({ length: 992 }, () => [token(2), token(3)]).flat(), token(3)]
  const built = tokensToTree(tokens, symbols)
  expect(built.ok).toBe(true)
  const latex = renderLatex(built.tree, symbols)
  expect(typeof renderPreview(built.tree, symbols)).toBe('string')
  expect(() => readTokens(tokens, symbols)).not.toThrow()
  expect(() => printFormula(tokens, symbols)).not.toThrow()
  const { container } = render(<><Latex>{latex}</Latex><span>page remains available</span></>)
  expect(container.querySelector('.katex') !== null || container.textContent?.includes('表示できない式')).toBe(true)
  expect(screen.getByText('page remains available')).toBeTruthy()
})

it('bounds giant dimensions and repeated font switches', () => {
  const spy = vi.spyOn(katex, 'renderToString')
  const { container, rerender } = render(<Latex>{'\\rule{999999em}{999999em}'}</Latex>)
  expect(container.querySelector('.katex')).toBeTruthy()
  expect(spy).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ trust: false, strict: 'warn', maxSize: 10, maxExpand: 1000 }))
  for (const node of container.querySelectorAll('[style]')) expect(node.getAttribute('style')).not.toMatch(/999999/)
  rerender(<Latex>{'\\Huge '.repeat(1000) + 'x'}</Latex>)
  expect(screen.getByText('表示できない式')).toBeTruthy()
})

it.each(['\\href{javascript:alert(1)}{x}', '\\includegraphics{https://untrusted.invalid/image}', '\\def\\loop{\\loop}\\loop'])('falls back for dangerous or unbounded input: %s', input => {
  const { container } = render(<Latex>{input}</Latex>)
  expect(screen.getByText('表示できない式')).toBeTruthy()
  expect(container.querySelector('a, img, script')).toBe(null)
})

it('contains non-parse exceptions from KaTeX', () => {
  vi.spyOn(katex, 'renderToString').mockImplementation(() => { throw new RangeError('stack overflow') })
  render(<><Latex>x</Latex><button>other controls</button></>)
  expect(screen.getByText('表示できない式')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'other controls' })).toBeTruthy()
})

it('contains conversion failures without inventing a formula', () => {
  const broken = new Proxy(symbols, { get() { throw new RangeError('stack overflow') } })
  expect(tokensToTree([token(3)], broken).ok).toBe(false)
  const built = tokensToTree([token(3)], symbols)
  expect(renderLatex(built.tree, broken)).toBe('表示できない式')
  expect(renderPreview(built.tree, broken)).toBe('表示できない式')
  expect(printFormula([token(3)], broken)).toBe(null)
  expect(readTokens([token(3)], broken)).toBe(null)
})


it('renders large formulas inside the display limits in both deployments', () => {
  const controlWordLimit = 2048
  const lengthLimit = 32_768
  const controlWords = controlWordLimit - 1
  const latex = ('\\neg '.repeat(controlWords) + 'P').padEnd(lengthLimit - 1, ' ')
  expect(latex.length).toBe(lengthLimit - 1)
  expect(latex.match(/\\[A-Za-z]+/g)).toHaveLength(controlWords)
  for (const beta of [false, true]) {
    const html = renderDisplayLatex(latex, false, beta)
    expect(html?.includes('class="katex"')).toBe(true)
    expect(html?.includes('katex-error')).toBe(false)
  }
})

it('rejects formulas immediately outside either display limit before rendering', () => {
  const spy = vi.spyOn(katex, 'renderToString')
  for (const beta of [false, true]) {
    expect(renderDisplayLatex('\\neg '.repeat(2048 + 1) + 'P', false, beta)).toBe(null)
    expect(renderDisplayLatex('P'.padEnd(32_768 + 1, ' '), false, beta)).toBe(null)
  }
  expect(spy).not.toHaveBeenCalled()
})

it('preserves pre-existing KaTeX error markup outside beta', () => {
  expect(renderDisplayLatex('\\frac{')).toContain('katex-error')
  expect(renderDisplayLatex('\\frac{', false, true)).toBe(null)
  for (const beta of [false, true]) {
    expect(renderDisplayLatex('\\text{katex-error Too many expansions}', false, beta)).toContain('class="katex"')
  }
})
