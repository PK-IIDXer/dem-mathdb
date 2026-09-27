import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { formulasApi } from '../../api/formulas'
import { symbolsApi } from '../../api/symbols'
import { Latex } from '../Latex'
import { renderLatex, renderPreview, tokensToTree } from '../FormulaEditor/model'

/** Fetches a Formula by id and renders it (LaTeX as the primary display, with
 * the polish/infix text kept as a small secondary caption). Many list
 * endpoints (Theorem, TheoremPremise, ProofStep) only embed the lightweight
 * Formula (no tokens), so a human-readable preview needs a follow-up fetch
 * for the token list. */
export function FormulaPreview({ formulaId, showTextPreview = true }: { formulaId: number; showTextPreview?: boolean }) {
  const { data: formula } = useQuery({
    queryKey: ['formulas', formulaId],
    queryFn: () => formulasApi.get(formulaId),
    // A formula's tokens are what its hash is taken over, and there is no
    // endpoint that edits one: a change is a different formula with a different
    // id. So a fetched formula never goes stale, and a view that primed this
    // cache in bulk (see ProofDetail) is not undone by a revalidation here.
    staleTime: Infinity,
  })
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const symbolsById = useMemo(() => new Map(symbols.map((s) => [s.id, s])), [symbols])
  const tree = useMemo(
    () => (formula ? tokensToTree(formula.tokens, symbolsById).tree : null),
    [formula, symbolsById],
  )
  const latex = useMemo(() => (tree ? renderLatex(tree, symbolsById) : null), [tree, symbolsById])
  const preview = useMemo(() => (tree ? renderPreview(tree, symbolsById) : null), [tree, symbolsById])
  if (!formula) return <span className="text-slate-400">読み込み中…</span>
  if (!tree) return <span className="text-red-700">この式は木で表示できません</span>
  return (
    <span>
      <Latex>{latex ?? ''}</Latex>
      {showTextPreview && <span className="ml-2 text-xs text-slate-400">{preview}</span>}
    </span>
  )
}
