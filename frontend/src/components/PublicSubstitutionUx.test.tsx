// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Axiom, BackwardStepSuggestion, FormulaDetail, ProofState, ProofStep, StepSuggestion, Symbol, Theorem } from '../api/types'
import { setLanguage } from '../i18n/language'
import fixture from '../test/fixtures/public-substitution-ux.json'
import { symbols as algebraSymbols } from '../test/fixtures/public-algebra.json'
import { PAGE_INTERACTION_TIMEOUT } from '../test/timeouts'
import { setupUser } from '../test/user'
import { StepJustification } from './ProofStepJustification'
import type { ProofPlanAction } from './proofPlanModel'
import { StepForm } from './StepForm/StepForm'
import { TopDownProofEditor } from './TopDownProofEditor'

const data = fixture as unknown as {
  axiom: Axiom
  lemma: Theorem
  equality: Theorem
  state: ProofState
  steps: ProofStep[]
  symbols: Symbol[]
  axiomSuggestion: StepSuggestion
  lemmaSuggestion: StepSuggestion
  backward: BackwardStepSuggestion[]
  formulas: FormulaDetail[]
}
const { axiom, lemma, equality, state, steps, symbols, axiomSuggestion, lemmaSuggestion } = data
const [first, quantified, last] = steps
const proofId = first.proof_id
const id = (name: string) => symbols.find((symbol) => symbol.name === name)!.id
const predicate = id('φ¹')
const term = id('t')
const parameter = id('w')
const formulas = new Map(data.formulas.map((formula) => [formula.id, formula]))
const { w, 'w ∈ a': member, 'v = u': equation } = fixture.inputIds
const body = formulas.get(member)!
const other = formulas.get(equation)!
const empty = { term_substs: [], prop_substs: [] }
const explicit = {
  term_substs: [{ source_symbol_id: term, target_formula_id: w }],
  prop_substs: [{ source_symbol_id: predicate, body_formula_id: member, formal_param_symbol_ids: [parameter] }],
}
const realBackward = data.backward.find((candidate) => candidate.match_depth === 1)!
const completed: BackwardStepSuggestion = {
  ...realBackward,
  subst: explicit,
  defaulted_to_identity: [],
  undetermined: [],
  application_conclusion_tokens: [
    { symbol_id: id('→'), de_bruijn_index: null },
    ...state.established.find((step) => step.ord === quantified.ord)!.tokens,
    ...state.goal_tokens,
  ],
  antecedent_goals: [state.established.find((step) => step.ord === quantified.ord)!.tokens],
  intermediate_conclusions: [state.goal_tokens],
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { 'Content-Type': 'application/json' },
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function setup({
  suggestion = axiomSuggestion,
  theorem = lemma,
  proofState = state,
  rejected,
  backward = completed,
}: {
  suggestion?: StepSuggestion
  theorem?: Theorem
  proofState?: typeof state
  rejected?: unknown
  backward?: BackwardStepSuggestion
} = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  })
  client.setQueryData(['theorems', lemma.id, 'premises'], [])
  client.setQueryData(['theorems', 'lemma-picker'], [theorem])
  client.setQueryData(['theorems', 'top-down-picker'], [])
  client.setQueryData(['axioms'], [axiom])
  client.setQueryData(['symbols'], symbols)
  client.setQueryData(['symbols', 'with-usage'], symbols)
  client.setQueryData(['symbol-aliases'], [])
  client.setQueryData(['formula-types'], [...new Map(data.formulas.map((formula) => [formula.formula_type.id, formula.formula_type])).values()])
  client.setQueryData(['proofs', proofId, 'state'], proofState)
  formulas.forEach((formula) => client.setQueryData(['formulas', formula.id], formula))
  const add = vi.fn()
  const suggest = vi.fn()
  vi.stubGlobal('fetch', (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const request = init?.body ? JSON.parse(String(init.body)) : null
    const root = '/api/proofs/' + proofId + '/steps'
    if (path === root + '/suggest-backward') return Promise.resolve(json({ candidates: [backward] }))
    if (path === root + '/suggest') {
      suggest(request)
      return Promise.resolve(json(suggestion))
    }
    if (path === root) {
      add(request)
      return Promise.resolve(rejected ? json(rejected, 422) : json({ ...first, ord: last.ord + 1 }, 201))
    }
    if (path.startsWith('/api/theorems/applicable?')) return Promise.resolve(json([]))
    if (path === '/api/formulas/parse') {
      const formulaId = fixture.inputIds[request.text as keyof typeof fixture.inputIds]
      const formula = formulas.get(formulaId)
      return Promise.resolve(formula
        ? json({ formula_id: formulaId, tokens: formula.tokens })
        : json({ detail: 'Incomplete formula' }, 422))
    }
    if (path === '/api/formulas/print') {
      const key = Object.keys(fixture.inputIds).find((label) => {
        const formula = formulas.get(fixture.inputIds[label as keyof typeof fixture.inputIds])!
        return formula.tokens.length === request.tokens.length && formula.tokens.every((token, index) => (
          token.symbol_id === request.tokens[index].symbol_id && token.de_bruijn_index === request.tokens[index].de_bruijn_index
        ))
      })
      return Promise.resolve(json({ text: key }))
    }
    const formula = formulas.get(Number(path.split('/').at(-1)))
    if (path.startsWith('/api/formulas/') && formula) return Promise.resolve(json(formula))
    throw new Error('Unexpected request: ' + path)
  })
  function mount(element: React.ReactNode) {
    return render(<MemoryRouter><QueryClientProvider client={client}>{element}</QueryClientProvider></MemoryRouter>)
  }
  return {
    add, suggest, mount,
    step: () => mount(<StepForm proofId={proofId} theoremId={lemma.id} priorSteps={steps} onAdded={() => undefined} showRules={false} />),
    plan: (dispatch: (action: ProofPlanAction) => void) => mount(
      <TopDownProofEditor proofId={proofId} proofState={proofState} symbols={symbols} context={{}}
        onAdded={() => undefined} onOperationDispatch={dispatch} showRules={false} />,
    ),
  }
}

const useAxiom = async (user: ReturnType<typeof setupUser>) => {
  await user.click(screen.getByRole('button', { name: 'Use an axiom' }))
  await user.selectOptions(screen.getByRole('combobox'), String(axiom.id))
}

async function useLemma(user: ReturnType<typeof setupUser>, theoremId: number, ords: number[], language: 'en' | 'ja' = 'en') {
  await user.click(screen.getByRole('button', { name: language === 'en' ? 'Use a lemma' : '補題を使う' }))
  for (const ord of ords) await user.click(screen.getByRole('checkbox', { name: '#' + ord }))
  await user.selectOptions(screen.getByRole('combobox', { name: language === 'en' ? 'Lemma to use' : '使う補題' }), String(theoremId))
}

async function enterFormula(user: ReturnType<typeof setupUser>, row: HTMLElement, text: keyof typeof fixture.inputIds) {
  await user.type(within(row).getByRole('textbox', { name: '' }), text)
  await user.click(await within(row).findByRole('button', { name: 'Select this formula' }))
}

describe('public substitution editing', { timeout: PAGE_INTERACTION_TIMEOUT }, () => {
  it.each([false, true])('opens both universal-elimination axiom identity rows (override: %s)', async (override) => {
    setLanguage('en')
    const { step, add } = setup()
    step()
    const user = setupUser()
    await useAxiom(user)
    const termRow = await screen.findByRole('group', { name: 't' })
    const propRow = screen.getByRole('group', { name: 'φ¹' })
    expect(within(termRow).getByText('Keep t unchanged')).toBeTruthy()
    expect(within(propRow).getByText('Keep φ¹ unchanged')).toBeTruthy()
    if (override) {
      await user.selectOptions(within(propRow).getByRole('combobox', { name: 'Parameter 1' }), String(parameter))
      await enterFormula(user, propRow, 'w ∈ a')
      await enterFormula(user, termRow, 'w')
    }
    await user.click(screen.getByRole('button', { name: 'Add this step' }))
    await waitFor(() => expect(add).toHaveBeenCalledWith({
      kind: 'axiom', axiom_id: axiom.id, subst: override ? explicit : empty,
    }))
  })

  it('submits an unchanged term override after choosing the universal-elimination argument', async () => {
    setLanguage('en')
    const { step, add, suggest } = setup({ suggestion: lemmaSuggestion })
    step()
    const user = setupUser()
    await useLemma(user, lemma.id, [quantified.ord])
    const termRow = await screen.findByRole('group', { name: 't' })
    expect(suggest).toHaveBeenCalledWith(expect.objectContaining({ arg_step_ords: [quantified.ord] }))
    await enterFormula(user, termRow, 'w')
    await user.click(screen.getByRole('button', { name: 'Add this step' }))
    await waitFor(() => expect(add).toHaveBeenCalledWith(expect.objectContaining({
      kind: 'theorem', arg_step_ords: [quantified.ord],
      subst: { ...lemmaSuggestion.subst, term_substs: explicit.term_substs },
    })))
  })

  it('requires a formula for an undetermined term', async () => {
    setLanguage('en')
    setup({ suggestion: {
      ...axiomSuggestion, defaulted_to_identity: [predicate],
      undetermined: [{ symbol_id: term, name: 't', reason: 'higher_order_pattern' }],
    } }).step()
    const user = setupUser()
    await useAxiom(user)
    const required = await screen.findByRole('region', { name: 'Required 1' })
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Add this step' })
    expect(button.disabled).toBe(true)
    await enterFormula(user, within(required).getByRole('group', { name: 't' }), 'w')
    expect(button.disabled).toBe(false)
  })

  it('avoids symbols in known formulas and substitution left sides and warns about an unused parameter', async () => {
    setLanguage('en')
    setup({
      proofState: { ...state, goal_tokens: other.tokens },
      suggestion: {
        ...axiomSuggestion,
        subst: { ...empty, term_substs: [{ source_symbol_id: id('y'), target_formula_id: w }] },
        conclusion_tokens: other.tokens,
      },
    }).step()
    const user = setupUser()
    await useAxiom(user)
    const row = await screen.findByRole('group', { name: 'φ¹' })
    const select = within(row).getByRole<HTMLSelectElement>('combobox', { name: 'Parameter 1' })
    expect(select.value).toBe(String(parameter))
    await enterFormula(user, row, 'v = u')
    expect(await within(row).findByText('These parameters do not occur free in the body (w).')).toBeTruthy()
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Add this step' }).disabled).toBe(false)
  })

  it('renders premise 2 and both formulas when the kernel rejects an argument', async () => {
    setLanguage('ja')
    const { step } = setup({
      theorem: equality,
      suggestion: {
        ...lemmaSuggestion, subst: empty, defaulted_to_identity: [],
        premise_count: 2, arg_slots: [0, 1], arg_candidates: [[quantified.ord], [last.ord]],
      },
      rejected: {
        code: 'proof.arg_mismatch', detail: 'Argument mismatch',
        details: { arg_index: 1, expected: body, actual: other },
      },
    })
    step()
    const user = setupUser()
    await useLemma(user, equality.id, [quantified.ord, last.ord], 'ja')
    await screen.findByRole('combobox', { name: /前提.*2/ })
    await user.click(screen.getByRole('button', { name: 'このステップを追加' }))
    const error = await screen.findByRole('alert')
    expect(error.textContent).toContain('前提 2 に選んだステップが、代入後の前提と一致しません。')
    expect(Array.from(error.querySelectorAll('dd annotation'), (element) => element.textContent)).toEqual([
      expect.stringMatching(/w.*(?:in|∈).*a/), expect.stringMatching(/v.*=.*u/),
    ])
  })

  it('disables the one-premise lemma when two steps are selected', async () => {
    setLanguage('en')
    const { step, suggest } = setup({ suggestion: lemmaSuggestion })
    step()
    await useLemma(setupUser(), lemma.id, [first.ord, quantified.ord])
    const option = screen.getByRole<HTMLOptionElement>('option', { name: /More selected steps than premises/ })
    expect(option.value).toBe(String(lemma.id))
    expect(option.disabled).toBe(true)
    expect(suggest).not.toHaveBeenCalled()
  })

  it.each([true, false])('lists all premises with formula previews (exact match: %s)', async (match) => {
    setLanguage('en')
    const { step } = setup({ suggestion: {
      ...lemmaSuggestion, arg_slots: [], arg_candidates: [match ? [quantified.ord] : []],
    } })
    step()
    await useLemma(setupUser(), lemma.id, [])
    const select = await screen.findByRole<HTMLSelectElement>('combobox', { name: /Premises: 1/ })
    const options = Array.from(select.options).slice(1)
    expect(options.map((option) => Number(option.value))).toEqual(match
      ? [quantified.ord, first.ord, last.ord]
      : steps.map((row) => row.ord))
    expect(options.find((option) => Number(option.value) === quantified.ord)!.textContent).toMatch(/∀.*∈.*a/)
    expect(options.find((option) => Number(option.value) === first.ord)!.textContent).toMatch(/x\s*=\s*x/)
    expect(options.find((option) => Number(option.value) === last.ord)!.textContent).toMatch(/v\s*=\s*u/)
    if (match) {
      expect(select.value).toBe(String(quantified.ord))
      expect(options[0].textContent).toContain('[Match]')
    } else {
      expect(select.value).toBe('-1')
      expect(select.selectedOptions[0].textContent).toBe('Select…')
      expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Add this step' }).disabled).toBe(true)
    }
  })

  it('applies a backward recipe with inferred substitutions immediately', async () => {
    setLanguage('ja')
    const dispatch = vi.fn()
    setup().plan(dispatch)
    await setupUser().selectOptions(screen.getByLabelText('公理を適用'), String(axiom.id))
    await waitFor(() => expect(dispatch).toHaveBeenCalledTimes(1))
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'apply_backward', application: expect.objectContaining({ subst: explicit }),
    }))
    expect(screen.queryByRole('button', { name: 'この代入で組み立てる' })).toBeNull()
  })

  it('waits for confirmation when a backward recipe has an identity default', async () => {
    setLanguage('ja')
    const dispatch = vi.fn()
    const { plan, add } = setup({ backward: {
      ...completed, defaulted_to_identity: [term], subst: { ...explicit, term_substs: [] },
    } })
    plan(dispatch)
    const user = setupUser()
    await user.selectOptions(screen.getByLabelText('公理を適用'), String(axiom.id))
    const confirm = await screen.findByRole('button', { name: 'この代入で組み立てる' })
    expect(screen.getByText('t のまま')).toBeTruthy()
    expect(dispatch).not.toHaveBeenCalled()
    expect(add).not.toHaveBeenCalled()
    await user.click(confirm)
    await waitFor(() => expect(dispatch).toHaveBeenCalledTimes(1))
  })

  it('renders saved term and proposition substitutions in assignment notation', async () => {
    setLanguage('en')
    const f = algebraSymbols.find((symbol) => symbol.name === 'f')! as Symbol
    setup().mount(<StepJustification
      step={{
        ...first, step_kind: 'axiom', axiom,
        prop_substs: explicit.prop_substs,
        term_substs: [{ source_symbol_id: f.id, target_formula_id: w }],
      }}
      symbolsById={new Map([...symbols, f].map((symbol) => [symbol.id, symbol]))}
      lemmas={new Map()} onJump={() => undefined}
    />)
    await setupUser().click(screen.getByRole('button', { name: /Substitution/ }))
    expect(screen.getByText('φ¹(w) :=').querySelector('annotation')?.textContent).toMatch(/w.*(?:in|∈).*a/)
    expect(screen.getByText('f :=').querySelector('annotation')?.textContent).toMatch(/w/)
  })
})

