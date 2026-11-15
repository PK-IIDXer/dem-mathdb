// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { formulasApi } from '../api/formulas'
import type { Symbol } from '../api/types'
import { setLanguage } from '../i18n/language'
import { publicSetCopy } from '../i18n/translate'
import fixture from '../test/fixtures/public-relations-maps.json'
import { CommandProvider } from '../commands/CommandProvider'
import { FormulaEditor } from './FormulaEditor/FormulaEditor'
import { Latex } from './Latex'
import { inferDefinitionKind } from './DefinitionKind/definitionKindInference'
import {
  buildSymbolCompletionItems, renderLatex, serialize, tokensToTree,
} from './FormulaEditor/model'

const symbols = fixture.symbols as Symbol[]
const byId = new Map(symbols.map(symbol => [symbol.id, symbol]))
afterEach(() => { cleanup(); vi.restoreAllMocks(); setLanguage('ja') })

it.each(['ja', 'en'] as const)('renders and serializes the public relations notation in %s', language => {
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

it('offers the public symbols for input and recognizes the definition kinds', () => {
  const completion = buildSymbolCompletionItems(symbols, new Map(), {})
  for (const name of ['∃!', '⊂', '×', 'IsRelation', 'IsMap', 'IsClassRelation', 'IsClassMap']) {
    expect(completion.some(item => item.symbol.name === name), name).toBe(true)
  }
  const phi = symbols.find(symbol => symbol.name === 'φ¹')!
  const x = symbols.find(symbol => symbol.name === 'x')!
  expect(inferDefinitionKind([{ symbolTypeName: phi.symbol_type.name, arity: 1 }], 'proposition')).toBe('quant_prop')
  expect(inferDefinitionKind(Array.from({ length: 3 }, () => ({
    symbolTypeName: x.symbol_type.name, arity: 0,
  })), 'proposition')).toBe('predicate')
})

it.each(['ja', 'en'] as const)('shows the requested names and explanatory copy in %s', language => {
  setLanguage(language)
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


it.each(['ja', 'en'] as const)('accepts relations and maps through the formula editor in %s', async language => {
  setLanguage(language)
  const samples = fixture.samples.filter(sample => [
    'IsMap(f, X, Y) → (∀ x.',
    'IsSet(X) → IsSet(Y) → IsMap(f, X, Y)',
    '∀ x. ∀ y. ∀ z. (IsMap(x, y, z))',
  ].some(start => sample.text.startsWith(start)))
  expect(samples).toHaveLength(3)
  const parse = vi.spyOn(formulasApi, 'parse').mockImplementation(async text => {
    const sample = samples.find(candidate => candidate.text === text)
    if (!sample) throw new Error('Unexpected formula input')
    return { tokens: sample.tokens, formula_id: null }
  })
  vi.spyOn(formulasApi, 'print').mockResolvedValue({ text: samples[0].text })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['symbols', 'with-usage'], symbols)
  client.setQueryData(['symbol-aliases'], [])
  client.setQueryData(
    ['formula-types'],
    Array.from(new Map(symbols.map(symbol => [symbol.symbol_type.id, symbol.symbol_type])).values()),
  )
  const view = render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <CommandProvider><FormulaEditor /></CommandProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
  const input = view.container.querySelector('textarea')!
  for (const sample of samples) {
    fireEvent.change(input, { target: { value: sample.text } })
    await waitFor(() => expect(parse).toHaveBeenLastCalledWith(sample.text, {}))
    await waitFor(() => expect(screen.getByRole('button', { name: /確認して登録する|Review and register/i })).not.toHaveProperty('disabled', true))
  }
})
