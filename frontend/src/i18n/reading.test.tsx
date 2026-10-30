// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import type { FormulaDetail, ProofStep, Symbol, Token } from '../api/types'
import { formulasApi } from '../api/formulas'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import { COMMON_READINGS, readTheoremSentence, readTokens } from '../components/FormulaReading/reading'
import { PropositionExplanation } from '../components/PropositionExplanation'
import fixture from '../test/fixtures/i18n-tutorial.json'
import { setupUser } from '../test/user'
import { setLanguage } from './language'

function symbol(id: number, name: string, arity: number, typeName = SYMBOL_TYPE.logical as string, quantifier = false): Symbol {
  return { id, public_id: `synthetic-${id}`, name, arity, symbol_type_id: id,
    symbol_type: { id, name: typeName, output_formula_type_id: 2, input_formula_type_id: null, fixed_arity: arity, is_quantifier: quantifier, remarks: null, created_at: '' },
    is_primitive: true, namespace_id: 1, namespace_name: 'synthetic', notation_kind: 'prefix', precedence: null, latex_template: null, remarks: null, created_at: '' }
}
const symbols = new Map<number, Symbol>()
const ids = new Map<string, number>()
for (const [publicId, reading] of COMMON_READINGS) {
  const id = symbols.size + 1
  const quantifier = reading.kind === 'forall' || reading.kind === 'exists'
  const arity = reading.kind === 'bot' ? 0 : reading.kind === 'not' || quantifier ? 1 : 2
  symbols.set(id, { ...symbol(id, reading.kind, arity, SYMBOL_TYPE.logical, quantifier), public_id: publicId })
  ids.set(reading.kind === 'relation' ? (ids.has('equals') ? 'member' : 'equals') : reading.kind, id)
}
symbols.set(20, symbol(20, 'P', 0, SYMBOL_TYPE.freePropositionVariable))
symbols.set(21, symbol(21, 'x', 0, SYMBOL_TYPE.freeTermVariable))
symbols.set(22, { ...symbol(22, 'Custom', 1, 'custom predicate type'), remarks: 'Custom(a): a が対象' })
const tok = (id: number): Token => ({ symbol_id: id, de_bruijn_index: null })
const tokens = (kind: string) => [tok(ids.get(kind)!), ...(kind === 'bot' ? [] : kind === 'not' || kind === 'forall' || kind === 'exists' ? [tok(20)] : ['equals', 'member'].includes(kind) ? [tok(21), tok(21)] : [tok(20), tok(20)])]
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it.each([
  ['bot', 'contradiction'], ['not', 'not the case'], ['and', ' and '], ['or', ' or '],
  ['imp', 'if '], ['iff', 'if and only if'], ['forall', 'for every term'],
  ['exists', 'there exists a term'], ['equals', ' equals '], ['member', 'is an element of'],
])('reads core %s in English', (kind, text) => {
  const reading = readTokens(tokens(kind), symbols, { language: 'en' })!
  expect(reading).not.toBeNull()
  expect(reading.language).toBe('en')
  expect(reading.sentence).toContain(text)
  expect(reading.sentence).not.toMatch(/[ぁ-んァ-ヶ一-龯]/u)
})

it('keeps the whole mixed formula and theorem reading Japanese', () => {
  setLanguage('en')
  const mixed = [tok(ids.get('and')!), tok(20), tok(22), tok(21)]
  const reading = readTokens(mixed, symbols)!
  const original = readTokens(mixed, symbols, { language: 'ja' })!
  expect(reading.language).toBe('ja')
  expect(reading.sentence).toBe(original.sentence)
  expect(reading.sentence).toContain('かつ')
  const core = readTokens(tokens('imp'), symbols)!
  const sentence = readTheoremSentence([core], reading)
  expect(sentence).toContain(core.japaneseSentence)
  expect(sentence).not.toMatch(/holds|if | and /)
})

it.each([false, true])('renders the reading language and foundation note, foundation=%s', async foundation => {
  setLanguage('en')
  const formulaTokens = foundation ? [tok(ids.get('and')!), tok(20), tok(22), tok(21)] : tokens('imp')
  vi.spyOn(formulasApi, 'get').mockResolvedValue({ ...fixture.onboarding.goal, tokens: formulaTokens } as FormulaDetail)
  vi.spyOn(formulasApi, 'namedConclusions').mockResolvedValue({ axioms: [], theorems: [] })
  const step = { ...fixture.onboarding.first_mp, conclusion_formula: { ...fixture.onboarding.goal, id: 900 } } as unknown as ProofStep
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>
    <PropositionExplanation step={step} symbolsById={symbols} lemmas={new Map()} trigger="Explain" />
  </MemoryRouter></QueryClientProvider>)
  await setupUser().click(screen.getByRole('button', { name: /Explain proposition at step/ }))
  const region = await screen.findByRole('region', { name: 'Mechanical reading' })
  const sentence = readTokens(formulaTokens, symbols)!.sentence
  const text = await within(region).findByText(sentence)
  expect(text.closest('[lang]')?.getAttribute('lang')).toBe(foundation ? 'ja' : 'en')
  expect(within(region).queryByText('This reading is generated from the symbol remarks in Japanese.') != null).toBe(foundation)
})
