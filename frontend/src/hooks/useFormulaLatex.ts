import { useMemo } from 'react'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { FORMULA_BATCH_MAX_IDS, formulasApi } from '../api/formulas'
import { symbolsApi } from '../api/symbols'
import { renderLatex, tokensToTree } from '../components/FormulaEditor/model'
import { symbolsWithDeclarationNames } from '../components/FormulaEditor/display'

export function useSymbolsById() {
  const { data: symbols = [] } = useQuery({ queryKey: ['symbols'], queryFn: () => symbolsApi.listSymbols() })
  return useMemo(() => new Map(symbols.map((s) => [s.id, s])), [symbols])
}

/** Fetches the formulas among `formulaIds` that are not cached yet in one
 * `GET /formulas/batch` and primes each `['formulas', id]` entry, so the
 * per-formula queries (FormulaPreview, useFormulaLatexList) become cache hits.
 * Returns the ids still waiting on that batch; empty once it settles. Only
 * those should hold back their per-formula query, so a formula that is already
 * cached keeps rendering. If the batch fails, they fall back to fetching one
 * formula at a time. */
export function usePrimeFormulas(formulaIds: number[]): ReadonlySet<number> {
  const queryClient = useQueryClient()
  // Keyed by the id set, so a new array with the same ids is not a new batch.
  const idsKey = [...new Set(formulaIds)].sort((a, b) => a - b).join(',')
  // Only re-read the cache when the id set changes: once the batch below has
  // primed the entries, recomputing would empty `missing` and change the key.
  const missing = useMemo(
    () =>
      idsKey === ''
        ? []
        : idsKey.split(',').map(Number).filter((id) => queryClient.getQueryData(['formulas', id]) === undefined),
    [idsKey, queryClient],
  )
  const { status } = useQuery({
    queryKey: ['formulas-batch', missing],
    queryFn: async () => {
      const chunks: number[][] = []
      for (let i = 0; i < missing.length; i += FORMULA_BATCH_MAX_IDS) {
        chunks.push(missing.slice(i, i + FORMULA_BATCH_MAX_IDS))
      }
      const results = await Promise.all(chunks.map((chunk) => formulasApi.getMany(chunk)))
      for (const formula of results.flat()) {
        queryClient.setQueryData(['formulas', formula.id], formula)
      }
      return missing.length
    },
    enabled: missing.length > 0,
    staleTime: Infinity,
  })
  const batchPending = missing.length > 0 && status === 'pending'
  return useMemo(() => (batchPending ? new Set(missing) : NO_IDS), [batchPending, missing])
}

const NO_IDS: ReadonlySet<number> = new Set()

/** Fetches each formula's full token list and renders it to a LaTeX string, for
 * callers that need to combine several formulas into one display block (e.g. a
 * theorem's "premises ⊢ conclusion" statement). Returns null per-entry while
 * that formula's tokens are still loading. */
export function useFormulaLatexList(
  formulaIds: number[], context: Record<string, number> = {},
): (string | null)[] {
  const symbolsById = useSymbolsById()
  const displaySymbolsById = useMemo(
    () => symbolsWithDeclarationNames(symbolsById, context),
    [context, symbolsById],
  )
  const waiting = usePrimeFormulas(formulaIds)
  const results = useQueries({
    queries: formulaIds.map((id) => ({
      queryKey: ['formulas', id],
      queryFn: () => formulasApi.get(id),
      // Same key and the same reason as FormulaPreview: a formula's tokens
      // never change, so this shares whatever any other view has already
      // fetched (or primed in bulk) instead of revalidating it.
      staleTime: Infinity,
      // Wait for the batch so these read the primed cache instead of racing it.
      enabled: !waiting.has(id),
    })),
  })
  return useMemo(
    () =>
      results.map((result) => {
        if (!result.data) return null
        const tree = tokensToTree(result.data.tokens, symbolsById).tree
        return tree ? renderLatex(tree, displaySymbolsById) : null
      }),
    [displaySymbolsById, results, symbolsById],
  )
}
