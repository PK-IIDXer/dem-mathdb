// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { explorationsApi } from '../api/explorations'
import { proofsApi } from '../api/proofs'
import { symbolsApi } from '../api/symbols'
import type { ExplorationNote, Formula, ProofStep, Symbol } from '../api/types'
import { ExplorationsPage } from './ExplorationsPage'

vi.mock('../components/FormulaPicker', () => ({
  FormulaPicker: ({ onChange }: { onChange: (id: number) => void }) => (
    <button type="button" onClick={() => onChange(111)}>命題を選ぶ</button>
  ),
}))

vi.mock('../components/FormulaPreview', () => ({
  FormulaPreview: ({ formulaId }: { formulaId: number }) => <span>式 {formulaId}</span>,
}))

vi.mock('../components/StepForm', () => ({
  StepForm: () => <div>推論入力</div>,
}))

vi.mock('../components/ProofStepList', () => ({
  ProofStepList: ({
    steps,
    onSelect,
    renderJustification,
  }: {
    steps: ProofStep[]
    onSelect?: (ord: number) => void
    renderJustification: (step: ProofStep, symbols: Map<number, Symbol>) => ReactNode
  }) => (
    <div>
      {steps.map((step) => (
        <div key={step.ord}>
          <button type="button" onClick={() => onSelect?.(step.ord)}>
            行 {step.ord} を選ぶ
          </button>
          <span>{renderJustification(step, new Map())}</span>
        </div>
      ))}
    </div>
  ),
}))

const formula = {
  id: 111,
  public_id: 'formula-111',
  formula_type_id: 1,
  hash: 'hash',
  token_count: 1,
  description: null,
  remarks: null,
  created_at: '2026-10-07T00:00:00Z',
} as Formula

const note = {
  theorem: {
    id: 10,
    public_id: '00000000-0000-4000-8000-000000000010',
    namespace_id: 1,
    namespace_name: 'dem.foundation.logic',
    name: '遊ぶノート',
    conclusion_formula_id: 112,
    conclusion_formula: formula,
    status: 'conjecture',
    description: null,
    tags: [],
    external_checks: [],
    remarks: null,
    created_at: '2026-10-07T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
  },
  proof: {
    id: 20,
    public_id: 'proof-20',
    theorem_id: 10,
    name: '遊ぶノート',
    status: 'draft',
    remarks: null,
    created_at: '2026-10-07T00:00:00Z',
    updated_at: '2026-10-07T00:00:00Z',
  },
  premises: [formula],
  step_count: 1,
  updated_at: '2026-10-07T00:00:00Z',
} as ExplorationNote

const step = {
  proof_id: 20,
  ord: 0,
  step_kind: 'premise',
  conclusion_formula: formula,
  premise_ord: 0,
  axiom: null,
  applied_proof_id: null,
  inference_rule: null,
  gen_variable_symbol_id: null,
  arg_step_ords: [],
  term_substs: [],
  prop_substs: [],
  remarks: null,
  created_at: '2026-10-07T00:00:00Z',
} as ProofStep

const theoremStep = {
  ...step,
  step_kind: 'theorem',
  premise_ord: null,
  applied_proof_id: 77,
} as ProofStep

function wrapper(initialEntry: string, path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    client,
    view: render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path={path} element={<ExplorationsPage />} />
            <Route path="/theorems/:id" element={<div>昇格した定理</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('推論ノート', () => {
  it('adds the navigation tab', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['config'], { read_only: false })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><App /></MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('link', { name: '推論ノート' })).toBeTruthy()
  })

  it('lists notes and creates one from a name and premise', async () => {
    vi.spyOn(explorationsApi, 'list').mockResolvedValue([note])
    const create = vi.spyOn(explorationsApi, 'create').mockResolvedValue(note)
    wrapper('/explorations', '/explorations')

    expect(await screen.findByText('遊ぶノート')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('名前'), { target: { value: '新しいノート' } })
    fireEvent.click(screen.getByRole('button', { name: '前提を追加' }))
    fireEvent.click(screen.getByRole('button', { name: '命題を選ぶ' }))
    fireEvent.click(screen.getByRole('button', { name: 'ノートを作る' }))

    await waitFor(() => expect(create).toHaveBeenCalledWith({
      name: '新しいノート',
      premise_formula_ids: [111],
    }))
  })

  it('shows dependencies for a selected line and promotes it', async () => {
    vi.spyOn(explorationsApi, 'get').mockResolvedValue(note)
    vi.spyOn(proofsApi, 'listSteps').mockResolvedValue([step])
    vi.spyOn(proofsApi, 'listFormulas').mockResolvedValue([])
    vi.spyOn(proofsApi, 'listDirectDependencies').mockResolvedValue({
      axioms: [],
      lemmas: [],
      applied_proofs: {},
    })
    vi.spyOn(symbolsApi, 'listSymbols').mockResolvedValue([])
    vi.spyOn(explorationsApi, 'lineDependencies').mockResolvedValue({
      axioms: [{ id: 30, public_id: 'axiom-30', name: '公理A' } as never],
      theorems: [{ id: 40, public_id: 'theorem-40', name: '定理B' } as never],
    })
    const promote = vi.spyOn(explorationsApi, 'promote').mockResolvedValue({
      theorem: { ...note.theorem, public_id: 'promoted-50', name: '昇格結果', status: 'proven' },
      proof: { ...note.proof, id: 50, status: 'verified' },
    })
    wrapper('/explorations/00000000-0000-4000-8000-000000000010', '/explorations/:id')

    fireEvent.click(await screen.findByRole('button', { name: '行 0 を選ぶ' }))
    expect(await screen.findByText('公理A')).toBeTruthy()
    expect(screen.getByText('定理B')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('新しい定理の名前'), { target: { value: '昇格結果' } })
    fireEvent.click(screen.getByRole('button', { name: '定理に昇格' }))

    await waitFor(() => expect(promote).toHaveBeenCalledWith('00000000-0000-4000-8000-000000000010', 0, '昇格結果'))
    expect(await screen.findByRole('link', { name: '昇格結果' })).toBeTruthy()
  })

  it('shows the cited theorem name in a theorem-step justification', async () => {
    vi.spyOn(explorationsApi, 'get').mockResolvedValue(note)
    vi.spyOn(proofsApi, 'listSteps').mockResolvedValue([theoremStep])
    vi.spyOn(proofsApi, 'listFormulas').mockResolvedValue([])
    vi.spyOn(symbolsApi, 'listSymbols').mockResolvedValue([])
    vi.spyOn(proofsApi, 'listDirectDependencies').mockResolvedValue({
      axioms: [],
      lemmas: [{
        proof_id: 55,
        theorem: { ...note.theorem, id: 40, public_id: 'theorem-40', name: '引用した定理' },
      }],
      applied_proofs: { 77: 40 },
      applied_proof_public_ids: { 77: '00000000-0000-4000-8000-000000000077' },
    })
    wrapper('/explorations/00000000-0000-4000-8000-000000000010', '/explorations/:id')

    expect(await screen.findByRole('link', { name: '引用した定理' })).toBeTruthy()
    expect(screen.queryByText('Proof #77')).toBeNull()
  })

  it('uses a number-free fallback when the cited theorem name is unavailable', async () => {
    vi.spyOn(explorationsApi, 'get').mockResolvedValue(note)
    vi.spyOn(proofsApi, 'listSteps').mockResolvedValue([theoremStep])
    vi.spyOn(proofsApi, 'listFormulas').mockResolvedValue([])
    vi.spyOn(symbolsApi, 'listSymbols').mockResolvedValue([])
    vi.spyOn(proofsApi, 'listDirectDependencies').mockResolvedValue({
      axioms: [],
      lemmas: [],
      applied_proofs: {},
    })
    wrapper('/explorations/00000000-0000-4000-8000-000000000010', '/explorations/:id')

    expect(await screen.findByText(/引用した証明/)).toBeTruthy()
    expect(screen.queryByText(/Proof #77/)).toBeNull()
  })
})
