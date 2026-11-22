// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { Symbol } from '../api/types'
import { setLanguage } from '../i18n/language'
import { publicSetCopy } from '../i18n/translate'
import fixture from '../test/fixtures/public-algebra.json'
import { Latex } from './Latex'
import { inferDefinitionKind } from './DefinitionKind/definitionKindInference'
import {
  buildSymbolCompletionItems, renderLatex, serialize, tokensToTree,
} from './FormulaEditor/model'

const symbols = fixture.symbols as Symbol[]
const byId = new Map(symbols.map(symbol => [symbol.id, symbol]))
afterEach(() => { cleanup(); setLanguage('ja') })

function latexOf(text: string) {
  const sample = fixture.samples.find(candidate => candidate.text === text)
  expect(sample, text).toBeDefined()
  const parsed = tokensToTree(sample!.tokens, byId)
  expect(parsed.ok, text).toBe(true)
  return renderLatex(parsed.tree, byId)
}

it.each(['ja', 'en'] as const)('renders and serializes the public algebra notation in %s', language => {
  setLanguage(language)
  for (const sample of fixture.samples) {
    const parsed = tokensToTree(sample.tokens, byId)
    expect(parsed.ok, sample.text).toBe(true)
    expect(serialize(parsed.tree)?.tokens.map(token => ({
      symbol_id: token.symbol_id ?? null,
      de_bruijn_index: token.de_bruijn_index ?? null,
    }))).toEqual(sample.tokens)
    const latex = renderLatex(parsed.tree, byId)
    expect(latex).not.toContain('#')
    expect(latex).not.toContain('square')
    const view = render(<Latex>{latex}</Latex>)
    expect(view.container.querySelector('.katex-error'), sample.text).toBeNull()
    expect(view.container.querySelector('.katex'), sample.text).not.toBeNull()
    view.unmount()
  }
})

it('writes the operation between its arguments and keeps the operation name', () => {
  const associativity = latexOf('(op(m, op(m, x, y), z)) = (op(m, x, op(m, y, z)))')
  expect(associativity).toContain('\\left(x \\cdot_{m} y\\right) \\cdot_{m} z')
  expect(associativity).toContain('x \\cdot_{m} \\left(y \\cdot_{m} z\\right)')
  expect(latexOf('(op(m, e, x)) = x')).toContain('e \\cdot_{m} x')
  expect(latexOf('IsSemigroup(S, m)')).toBe('\\left(S, m\\right) \\mathrel{\\mathsf{IsSemigroup}}')
  expect(latexOf('IsMonoid(S, m, e)')).toBe('\\left(S, m, e\\right) \\mathrel{\\mathsf{IsMonoid}}')
})

it('offers the algebra symbols for input and recognizes the definition kinds', () => {
  const completion = buildSymbolCompletionItems(symbols, new Map(), {})
  for (const name of ['op', 'IsSemigroup', 'IsMonoid']) {
    expect(completion.some(item => item.symbol.name === name), name).toBe(true)
  }
  const x = symbols.find(symbol => symbol.name === 'x')!
  const terms = (count: number) => Array.from({ length: count }, () => ({
    symbolTypeName: x.symbol_type.name, arity: 0,
  }))
  expect(inferDefinitionKind(terms(3), 'term')).toBe('function')
  expect(inferDefinitionKind(terms(2), 'proposition')).toBe('predicate')
  expect(inferDefinitionKind(terms(3), 'proposition')).toBe('predicate')
})

it.each(['ja', 'en'] as const)('shows the algebra names and explanatory copy in %s', language => {
  setLanguage(language)
  expect(fixture.copy).toHaveLength(20)
  for (const row of fixture.copy) {
    const copy = publicSetCopy(row.id)
    expect(copy?.name).toBe(row[language])
    expect(copy?.description.trim()).toBeTruthy()
    const title = copy!.name.replace(/^[^:]+:\s*/, '')
    for (const ending of ['。', '.']) {
      expect(copy!.description.trim()).not.toBe(copy!.name + ending)
      expect(copy!.description.trim()).not.toBe(title + ending)
    }
  }
})
