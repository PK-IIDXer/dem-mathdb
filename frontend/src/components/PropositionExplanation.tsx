import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { UserSymbolNotice } from './BetaIdentity'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { formulasApi } from '../api/formulas'
import { theoremsApi } from '../api/theorems'
import { useCommand } from '../commands/CommandProvider'
import { SYMBOL_TYPE } from '../constants/symbolTypes'
import { usePrimeFormulas } from '../hooks/useFormulaLatex'
import { FormulaPreview } from './FormulaPreview'
import { itemMarker, readTheoremSentence, readTokens, type FormulaReading, type ReadingBlock } from './FormulaReading/reading'
import type { LemmaDependency, ProofStep, Symbol } from '../api/types'

interface Props {
  step: ProofStep
  symbolsById: Map<number, Symbol>
  lemmas: Map<number, LemmaDependency>
  trigger: ReactNode
  onShowInList?: (ord: number) => void
  className?: string
}

const RULE_TAG = 'system:rule'
const NO_FORMULA_IDS: number[] = []

export function PropositionExplanation({ step, symbolsById, lemmas, trigger, onShowInList, className }: Props) {
  const language = useLanguage()

  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const { data, isError } = useQuery({
    queryKey: ['formulas', step.conclusion_formula.id, 'named-conclusions'],
    queryFn: () => formulasApi.namedConclusions(step.conclusion_formula.id),
    enabled: open,
    // A new theorem or axiom can later claim the same immutable formula.
    // Recheck on the next open, never while the row is merely rendered.
    staleTime: 0,
  })
  // The proof view primes every step formula in one request, so this is a
  // cache read; it stays disabled until the popover opens either way.
  const { data: formula } = useQuery({
    queryKey: ['formulas', step.conclusion_formula.id],
    queryFn: () => formulasApi.get(step.conclusion_formula.id),
    enabled: open,
    staleTime: Infinity,
  })
  const reading = useMemo(
    () => (open && formula ? readTokens(formula.tokens, symbolsById, { language }) : undefined),
    [formula, language, open, symbolsById],
  )

  const lemma = step.applied_proof_id == null ? undefined : lemmas.get(step.applied_proof_id)
  const source = step.step_kind === 'axiom' ? step.axiom : lemma?.theorem
  const sourcePath = step.step_kind === 'axiom'
    ? source && `/axioms/${source.public_id}`
    : source && `/theorems/${source.public_id}`
  const ruleTheorem = step.step_kind === 'theorem' && lemma?.theorem.tags?.some((tag) => tag.name === RULE_TAG)
    ? lemma.theorem
    : undefined
  const ruleReading = useRuleTheoremReading(open ? ruleTheorem : undefined, symbolsById)

  function close() {
    setOpen(false)
    triggerRef.current?.focus()
  }
  // Escape goes through the N8 command registry: it closes this popover only
  // while focus is inside it, and yields to the command palette when that is
  // open on top. The dispatcher also ignores IME composition.
  useCommand('explanation.close', close, { enabled: open, scope: dialogRef })

  useEffect(() => {
    if (!open) return
    const anchor = triggerRef.current?.getBoundingClientRect()
    if (anchor) setPosition({ top: anchor.bottom + 8, left: Math.max(8, Math.min(anchor.left, window.innerWidth - 488)) })
    closeRef.current?.focus()
  }, [open])

  useEffect(() => {
    if (!open || !dialogRef.current) return
    const rect = dialogRef.current.getBoundingClientRect()
    if (rect.bottom > window.innerHeight - 8) {
      setPosition((current) => ({ ...current, top: Math.max(8, window.innerHeight - rect.height - 8) }))
    }
  }, [open, data, reading, ruleReading])

  return (
    <span className="relative inline-block align-baseline">
      <UserSymbolNotice formulaIds={[step.conclusion_formula.id]} />
      <button ref={triggerRef} type="button" className={className ?? 'text-indigo-700 hover:underline'}
        aria-label={t("PropositionExplanation_323", step.ord)} aria-expanded={open}
        onClick={() => setOpen(true)}>{trigger}</button>
      {open && createPortal(
        <div ref={dialogRef} role="dialog" aria-label={t("PropositionExplanation_324", step.ord)}
          style={{ top: position.top, left: position.left }}
          className="fixed z-50 max-h-[70vh] w-[min(30rem,90vw)] overflow-auto rounded-lg border border-slate-300 bg-white p-4 text-left text-sm normal-case text-slate-800 shadow-xl">
          <span className="mb-2 flex items-center justify-between gap-3">
            <strong>{t("PropositionExplanation_325")}{step.ord})</strong>
            <button ref={closeRef} type="button" onClick={close} className="text-indigo-700 hover:underline">{t("CommandPalette_041")}</button>
          </span>
          <span className="mb-2 block break-words text-base"><FormulaPreview formulaId={step.conclusion_formula.id} /></span>
          <MechanicalReading reading={reading} loading={formula === undefined} />
          <span className="mt-2 block">{describeStep(step, source?.name, symbolsById)}</span>
          {sourcePath && <Link to={sourcePath} className="mt-1 block text-indigo-700 hover:underline">{source?.name} {t("PropositionExplanation_327")}</Link>}
          {source?.description && <span className="mt-2 block">{t("PropositionExplanation_328")}{source.description}</span>}
          {ruleTheorem && (
            <section className="mt-2" aria-label={t("PropositionExplanation_329")}>
              <span className="block text-xs font-semibold text-slate-500">{t("PropositionExplanation_330")}{ruleTheorem.name}{t("PropositionExplanation_331")}</span>
              <span lang={ruleReading?.language} className="block break-words">{ruleReading?.sentence ?? (ruleReading === null ? t("PropositionExplanation_332") : t("BetaGettingStarted_109"))}</span>
            {language === 'en' && ruleReading?.language === 'ja' && <span className="block text-xs text-slate-500">{t('readingJapaneseNote')}</span>}
            </section>
          )}
          {data ? (
            <span className="mt-2 block">
              {data.theorems.map((item) => <span key={`theorem-${item.public_id}`} className="block">
                {t("PropositionExplanation_334")}<Link to={`/theorems/${item.public_id}`} className="text-indigo-700 hover:underline">{item.name}</Link>{t("PropositionExplanation_335")}{item.description && ` — ${item.description}`}
              </span>)}
              {data.axioms.map((item) => <span key={`axiom-${item.public_id}`} className="block">
                {t("PropositionExplanation_336")}<Link to={`/axioms/${item.public_id}`} className="text-indigo-700 hover:underline">{item.name}</Link>{t("PropositionExplanation_335")}{item.description && ` — ${item.description}`}
              </span>)}
            </span>
          ) : isError ? <span role="alert" className="mt-2 block text-red-700">{t("PropositionExplanation_338")}</span>
            : <span className="mt-2 block text-slate-500">{t("PropositionExplanation_339")}</span>}
          {step.conclusion_formula.remarks && <span className="mt-2 block">{t("PropositionExplanation_340")}{step.conclusion_formula.remarks}</span>}
          {reading && <SymbolMeanings reading={reading} symbolsById={symbolsById} />}
          {onShowInList && <button type="button" onClick={() => { close(); onShowInList(step.ord) }} className="mt-3 block text-indigo-700 hover:underline">{t("PropositionExplanation_341")}</button>}
        </div>, document.body,
      )}
    </span>
  )
}

/** Reads a `system:rule` theorem with its premises. Fetches the premise list
 * and the missing formulas only while a popover showing it is open. */
function useRuleTheoremReading(
  theorem: LemmaDependency['theorem'] | undefined,
  symbolsById: Map<number, Symbol>,
): { sentence: string; language: 'ja' | 'en' } | null | undefined {
  const language = useLanguage()
  const { data: premises } = useQuery({
    queryKey: ['theorems', theorem?.id, 'premises'],
    queryFn: () => theoremsApi.listPremises(theorem!.id),
    enabled: theorem != null,
  })
  const formulaIds = useMemo(
    () => (theorem && premises ? [...premises.map((premise) => premise.formula.id), theorem.conclusion_formula_id] : NO_FORMULA_IDS),
    [premises, theorem],
  )
  const waiting = usePrimeFormulas(formulaIds)
  const results = useQueries({
    queries: formulaIds.map((id) => ({
      queryKey: ['formulas', id],
      queryFn: () => formulasApi.get(id),
      staleTime: Infinity,
      enabled: !waiting.has(id),
    })),
  })
  return useMemo(() => {
    if (!theorem || formulaIds.length === 0 || results.some((result) => !result.data)) return undefined
    const readings = results.map((result) => readTokens(result.data!.tokens, symbolsById, { language }))
    if (readings.some((item) => item === null)) return null
    const all = readings as FormulaReading[]
    return { sentence: readTheoremSentence(all.slice(0, -1), all[all.length - 1]), language: all.every(reading => reading.language === 'en') ? 'en' : 'ja' }
  }, [formulaIds.length, language, results, symbolsById, theorem])
}

function MechanicalReading({ reading, loading }: { reading: FormulaReading | null | undefined; loading: boolean }) {
  const language = useLanguage()

  return (
    <section className="mt-1 rounded bg-slate-50 px-2 py-1.5" aria-label={t("PropositionExplanation_342")}>
      <span className="block text-xs font-semibold text-slate-500">{t("PropositionExplanation_342")}</span>
      {reading ? <span lang={reading.language}><ReadingBlockView block={reading.block} /></span>
        : <span className="block text-slate-500">{loading ? t("BetaGettingStarted_109") : t("PropositionExplanation_332")}</span>}
      {language === 'en' && reading?.language === 'ja' && <span className="block text-xs text-slate-500">{t('readingJapaneseNote')}</span>}
    </section>
  )
}

function ReadingBlockView({ block }: { block: ReadingBlock }) {
  useLanguage()

  if (!block.items) return <span className="block break-words">{block.text}</span>
  return (
    <>
      <span className="block break-words">{block.text}:</span>
      <ol className="ml-1 border-l border-slate-200 pl-2">
        {block.items.map((item, index) => (
          <li key={index} className="flex gap-1">
            <span aria-hidden="true">{itemMarker(index)}</span>
            <span className="min-w-0 flex-1"><ReadingBlockView block={item} /></span>
          </li>
        ))}
      </ol>
    </>
  )
}

const VARIABLE_TYPES = new Set<string>([SYMBOL_TYPE.freeTermVariable, SYMBOL_TYPE.freePropositionVariable])

function SymbolMeanings({ reading, symbolsById }: { reading: FormulaReading; symbolsById: Map<number, Symbol> }) {
  useLanguage()

  const fallback = new Set(reading.nameFallbackSymbolIds)
  const symbols = reading.symbolIds
    .map((id) => symbolsById.get(id))
    .filter((symbol): symbol is Symbol => symbol != null && !VARIABLE_TYPES.has(symbol.symbol_type.name))
  if (symbols.length === 0) return null
  return (
    <section className="mt-2" aria-label={t("PropositionExplanation_346")}>
      <span className="block text-xs font-semibold text-slate-500">{t("PropositionExplanation_346")}</span>
      <dl className="mt-0.5">
        {symbols.map((symbol) => (
          <div key={symbol.id} className="flex gap-2">
            <dt className="shrink-0 font-mono">{symbol.name}</dt>
            <dd className="min-w-0 break-words text-slate-600">
              {symbol.remarks ?? t("PropositionExplanation_348")}
              {fallback.has(symbol.id) && <span className="text-slate-400">{t("PropositionExplanation_349")}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function describeStep(step: ProofStep, sourceName: string | undefined, symbols: Map<number, Symbol>): string {
  const refs = step.arg_step_ords.map((ord) => `step (${ord})`).join('、')
  switch (step.step_kind) {
    case 'premise': return t("PropositionExplanation_350", step.premise_ord)
    case 'assumption': return t("PropositionExplanation_351")
    case 'axiom': return t("PropositionExplanation_352", sourceName ?? t("PropositionExplanation_353"))
    case 'theorem': return t("PropositionExplanation_354", sourceName ? t("PropositionExplanation_355", sourceName) : t("PropositionExplanation_356"), refs ? t("PropositionExplanation_357", refs) : '')
    case 'rule':
      if (step.inference_rule?.kind === 'modus_ponens') return `MP (${refs})`
      if (step.inference_rule?.kind === 'generalization') return t("PropositionExplanation_358", refs, step.gen_variable_symbol_id != null ? t("PropositionExplanation_359", symbols.get(step.gen_variable_symbol_id)?.name ?? `#${step.gen_variable_symbol_id}`) : '')
      if (step.inference_rule?.kind === 'implication_intro') return t("PropositionExplanation_360", refs)
      return step.inference_rule?.kind ?? t("PropositionExplanation_361")
    default: return step.step_kind
  }
}
