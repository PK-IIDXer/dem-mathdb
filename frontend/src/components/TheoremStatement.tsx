import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { useFormulaLatexList } from '../hooks/useFormulaLatex'
import { Latex } from './Latex'

/** Renders a theorem's statement as one display-mode LaTeX block in the
 * `premise, premise, ... ⊢ conclusion` form mathematicians actually read,
 * instead of the premise/conclusion list scattered across separate rows. */
export function TheoremStatement({ theoremId, context = {} }: {
  theoremId: number
  context?: Record<string, number>
}) {
  const { data: theorem } = useQuery({
    queryKey: ['theorems', theoremId],
    queryFn: () => theoremsApi.get(theoremId),
  })
  const { data: premises } = useQuery({
    queryKey: ['theorems', theoremId, 'premises'],
    queryFn: () => theoremsApi.listPremises(theoremId),
  })

  // Settled only once both reads are in: ids that grew in two steps would split
  // the formula batch into two requests (the theorem page's own theorem query is
  // keyed by public id, so the two often arrive separately).
  const formulaIds = useMemo(
    () => (theorem && premises ? [...premises.map((p) => p.formula.id), theorem.conclusion_formula_id] : []),
    [premises, theorem],
  )
  const latexList = useFormulaLatexList(formulaIds, context)

  if (!theorem) return <span className="text-sm text-slate-400">読み込み中…</span>

  const premiseCount = premises?.length ?? 0
  const premiseLatex = latexList.slice(0, premiseCount)
  const conclusionLatex = latexList[premiseCount]
  const ready = conclusionLatex != null && premiseLatex.every((l) => l != null)

  const combined = ready
    ? premiseLatex.length > 0
      ? `${premiseLatex.join(',\\quad ')} \\;\\vdash\\; ${conclusionLatex}`
      : `\\vdash\\; ${conclusionLatex}`
    : null

  return (
    <div className="overflow-x-auto rounded border border-slate-100 bg-white px-4 py-5">
      {combined ? (
        <Latex display>{combined}</Latex>
      ) : (
        <span className="text-sm text-slate-400">数式を読み込み中…</span>
      )}
    </div>
  )
}
