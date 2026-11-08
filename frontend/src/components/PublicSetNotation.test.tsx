// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { Symbol } from '../api/types'
import fixture from '../test/fixtures/public-zfc-mk.json'
import { setLanguage } from '../i18n/language'
import { Latex } from './Latex'
import { inferDefinitionKind } from './DefinitionKind/definitionKindInference'
import { buildSymbolCompletionItems, renderLatex, renderTemplateSample, serialize, tokensToTree } from './FormulaEditor/model'

const symbols = fixture.symbols as Symbol[]
const byId = new Map(symbols.map(s => [s.id, s]))
afterEach(() => { cleanup(); setLanguage('ja') })

it.each(['ja', 'en'] as const)('renders and serializes actual public notation in %s', language => {
  setLanguage(language)
  for (const sample of fixture.samples) {
    const parsed = tokensToTree(sample.tokens, byId)
    expect(parsed.ok, sample.text).toBe(true)
    expect(serialize(parsed.tree)?.tokens.map(token => ({ symbol_id: token.symbol_id ?? null,
      de_bruijn_index: token.de_bruijn_index ?? null }))).toEqual(sample.tokens)
    const latex = renderLatex(parsed.tree, byId)
    expect(latex).not.toContain('#')
    expect(latex).not.toContain('square')
    const view = render(<Latex>{latex}</Latex>)
    expect(view.container.querySelector('.katex-error')).toBeNull()
    expect(view.container.querySelector('.katex')).not.toBeNull()
    view.unmount()
  }
  for (const name of ['IsSet', '{|}', '{}', '{,}', '⟨,⟩']) {
    const symbol = symbols.find(s => s.name === name)!
    const view = render(<Latex>{renderTemplateSample(symbol.latex_template!, symbol.symbol_type.is_quantifier)}</Latex>)
    expect(view.container.querySelector('.katex-error')).toBeNull()
    view.unmount()
  }
})

it('offers the actual binder and ordered pair in input completion', () => {
  const items = buildSymbolCompletionItems(symbols, new Map(), {})
  for (const name of ['IsSet', '{|}', '⟨,⟩', 'φ²']) {
    const symbol = symbols.find(s => s.name === name)!
    expect(items.some(item => item.symbol.id === symbol.id)).toBe(true)
  }
  const phi = symbols.find(s => s.name === 'φ¹')!
  expect(inferDefinitionKind([{ symbolTypeName: phi.symbol_type.name, arity: phi.arity }], 'term')).toBe('quant_term')
})

it('preserves the arity mark when rendering the binary proposition variable', () => {
  const symbol = (name: string) => symbols.find(s => s.name === name)!
  expect(symbol('φ²').is_primitive).toBe(false)
  for (const name of ['φ¹', 'φ²', 'φ³']) expect(symbol(name).latex_template).toBeNull()
  const tokens = ['φ²', 'a', 'b'].map(name => ({ symbol_id: symbol(name).id }))
  const parsed = tokensToTree(tokens, byId)
  expect(parsed.ok).toBe(true)
  const latex = renderLatex(parsed.tree, byId)
  expect(latex).toBe('φ²\\left(a, b\\right)')
  const view = render(<Latex>{latex}</Latex>)
  expect(view.container.querySelector('.katex-error')).toBeNull()
  expect(view.container.querySelector('.katex')).not.toBeNull()
})
