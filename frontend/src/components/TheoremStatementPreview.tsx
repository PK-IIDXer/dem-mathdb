import { Fragment } from 'react'
import type { Theorem } from '../api/types'
import { t } from '../i18n/translate'
import { useLanguage } from '../i18n/useLanguage'
import { FormulaPreview } from './FormulaPreview'
import { Latex } from './Latex'

type Statement = Pick<Theorem, 'premise_formula_ids' | 'conclusion_formula_id'>

export function theoremFormulaIds(theorem: Statement): number[] {
  return [...theorem.premise_formula_ids, theorem.conclusion_formula_id]
}

export function TheoremStatementPreview({ theorem, formulasWaiting }: {
  theorem: Statement
  formulasWaiting: ReadonlySet<number>
}) {
  useLanguage()

  const { premise_formula_ids: premises, conclusion_formula_id: conclusion } = theorem
  if (theoremFormulaIds(theorem).some((id) => formulasWaiting.has(id))) {
    return <span className="text-slate-400">{t("BetaGettingStarted_109")}</span>
  }

  return (
    <span className="block min-w-0 max-w-full overflow-x-auto whitespace-nowrap">
      {premises.map((id, ord) => (
        <Fragment key={ord}>
          <FormulaPreview formulaId={id} showTextPreview={false} />
          <Latex>{ord + 1 < premises.length ? ',\\quad' : '\\;\\vdash\\;'}</Latex>
        </Fragment>
      ))}
      <FormulaPreview formulaId={conclusion} showTextPreview={premises.length === 0} />
    </span>
  )
}

