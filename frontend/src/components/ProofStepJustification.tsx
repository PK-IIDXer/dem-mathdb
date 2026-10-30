import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { LemmaDependency, ProofStep, PropSubst, Symbol, TermSubst } from '../api/types'
import { FormulaPreview } from './FormulaPreview'

export function StepRef({ ord, onJump }: { ord: number; onJump: (ord: number) => void }) {
  useLanguage()

  return (
    <button type="button" onClick={() => onJump(ord)} className="text-indigo-600 hover:underline">
      ({ord})
    </button>
  )
}

function StepRefList({ ords, onJump }: { ords: number[]; onJump: (ord: number) => void }) {
  useLanguage()

  return (
    <>
      {ords.map((ord, index) => (
        <span key={ord}>
          {index > 0 && ', '}
          <StepRef ord={ord} onJump={onJump} />
        </span>
      ))}
    </>
  )
}

function SubstSummary({
  termSubsts,
  propSubsts,
  symbolsById,
}: {
  termSubsts: TermSubst[]
  propSubsts: PropSubst[]
  symbolsById: Map<number, Symbol>
}) {
  useLanguage()

  const [open, setOpen] = useState(false)
  if (termSubsts.length === 0 && propSubsts.length === 0) return null
  return (
    <span className="ml-1">
      <button type="button" onClick={() => setOpen((value) => !value)} className="text-slate-400 hover:text-slate-600">
        {t("ProofStepJustification_288")}{open ? '▲' : '▼'}]
      </button>
      {open && (
        <span className="ml-1 inline-flex flex-wrap items-center gap-x-2">
          {termSubsts.map((subst, index) => (
            <span key={`t${index}`} className="whitespace-nowrap">
              {symbolsById.get(subst.source_symbol_id)?.name ?? `#${subst.source_symbol_id}`} ↦{' '}
              <FormulaPreview formulaId={subst.target_formula_id} />
            </span>
          ))}
          {propSubsts.map((subst, index) => (
            <span key={`p${index}`} className="whitespace-nowrap">
              {symbolsById.get(subst.source_symbol_id)?.name ?? `#${subst.source_symbol_id}`} ↦{' '}
              <FormulaPreview formulaId={subst.body_formula_id} />
            </span>
          ))}
        </span>
      )}
    </span>
  )
}

export function StepJustification({
  step,
  symbolsById,
  lemmas,
  onJump,
}: {
  step: ProofStep
  symbolsById: Map<number, Symbol>
  lemmas: Map<number, LemmaDependency>
  onJump: (ord: number) => void
}) {
  useLanguage()

  switch (step.step_kind) {
    case 'premise':
      return <span>{t("ProofStepJustification_289")}{step.premise_ord}</span>
    case 'assumption':
      return <span>{t("ProofStepJustification_290")}</span>
    case 'axiom':
      return (
        <span>
          {t("ProofStepJustification_291")}{' '}
          {step.axiom ? (
            <Link to={`/axioms/${step.axiom.public_id}`} className="text-indigo-600 hover:underline">
              {step.axiom.name}
            </Link>
          ) : (
            '?'
          )}
          <SubstSummary termSubsts={step.term_substs} propSubsts={step.prop_substs} symbolsById={symbolsById} />
        </span>
      )
    case 'theorem': {
      const lemma = step.applied_proof_id == null ? undefined : lemmas.get(step.applied_proof_id)
      return (
        <span>
          {t("ProofStepJustification_292")}{' '}
          {lemma?.proof_public_id ? (
            <Link to={`/proofs/${lemma.proof_public_id}`} className="text-indigo-600 hover:underline">
              {lemma.theorem.name}
            </Link>
          ) : (lemma?.theorem.name ?? t("ProofStepJustification_293"))}
          {step.arg_step_ords.length > 0 && (
            <>
              {' '}
              (<StepRefList ords={step.arg_step_ords} onJump={onJump} />)
            </>
          )}
          <SubstSummary termSubsts={step.term_substs} propSubsts={step.prop_substs} symbolsById={symbolsById} />
        </span>
      )
    }
    case 'rule':
      if (step.inference_rule?.kind === 'modus_ponens') {
        return (
          <span>
            MP <StepRefList ords={step.arg_step_ords} onJump={onJump} />
          </span>
        )
      }
      if (step.inference_rule?.kind === 'generalization') {
        return (
          <span>
            Gen <StepRefList ords={step.arg_step_ords} onJump={onJump} />
            {step.gen_variable_symbol_id != null && (
              <> (var: {symbolsById.get(step.gen_variable_symbol_id)?.name ?? `#${step.gen_variable_symbol_id}`})</>
            )}
          </span>
        )
      }
      if (step.inference_rule?.kind === 'implication_intro') {
        const [assumptionOrd, bodyOrd] = step.arg_step_ords
        return (
          <span>
            {t("ProofStepJustification_294")}<StepRefList ords={assumptionOrd != null ? [assumptionOrd] : []} onJump={onJump} /> {t("ProofStepJustification_295")}{' '}
            <StepRefList ords={bodyOrd != null ? [bodyOrd] : []} onJump={onJump} /> {t("ProofStepJustification_296")}</span>
        )
      }
      return <span>{step.inference_rule?.kind ?? 'rule'}</span>
    default:
      return null
  }
}
