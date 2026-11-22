import type { StepSuggestion, Substitution, Symbol, Token } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'

export type Inference = Pick<StepSuggestion, 'subst' | 'undetermined' | 'defaulted_to_identity'>

export interface SubstitutionDraft {
  value: Substitution
  unfinished: number[]
}

export function substitutionGroups(inference: Inference) {
  const determined = [
    ...inference.subst.term_substs.map((item) => item.source_symbol_id),
    ...inference.subst.prop_substs.map((item) => item.source_symbol_id),
  ]
  const filled = new Set(determined)
  const required = inference.undetermined.map((item) => item.symbol_id).filter((id) => !filled.has(id))
  const requiredIds = new Set(required)
  const identity = inference.defaulted_to_identity.filter((id) => !filled.has(id) && !requiredIds.has(id))
  return { determined, identity, required }
}

export function createSubstitutionDraft(inference: Inference, symbols: Symbol[], formulas: Token[][]): SubstitutionDraft {
  const ids = substitutionGroups(inference)
  const blankIds = new Set([...ids.identity, ...ids.required])
  const used = new Set([
    ...ids.determined, ...blankIds,
    ...formulas.flatMap((tokens) => tokens.map((token) => token.symbol_id)),
  ])
  const availableParams = symbols.filter((symbol) => (
    symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable && !used.has(symbol.id)
  ))
  const value: Substitution = {
    term_substs: [...inference.subst.term_substs],
    prop_substs: [...inference.subst.prop_substs],
  }
  for (const symbol of symbols) {
    if (!blankIds.has(symbol.id)) continue
    if (symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable) {
      value.term_substs.push({ source_symbol_id: symbol.id, target_formula_id: 0 })
    } else if (symbol.symbol_type.name === SYMBOL_TYPE.freePropositionVariable) {
      value.prop_substs.push({
        source_symbol_id: symbol.id,
        body_formula_id: 0,
        formal_param_symbol_ids: Array.from({ length: symbol.arity }, (_, index) => availableParams[index]?.id ?? 0),
      })
    }
  }
  return { value, unfinished: [] }
}

export function completedSubstitution(
  inference: Inference,
  draft: SubstitutionDraft,
  symbolsById: Map<number, Symbol>,
): Substitution | null {
  if (draft.unfinished.length > 0) return null

  const term_substs = draft.value.term_substs.filter((item) => item.target_formula_id > 0)
  const prop_substs = draft.value.prop_substs.filter((item) => item.body_formula_id > 0)
  const filled = new Set([...term_substs, ...prop_substs].map((item) => item.source_symbol_id))
  const ids = substitutionGroups(inference)
  if ([...ids.determined, ...ids.required].some((id) => !filled.has(id))) return null
  if (!prop_substs.every((item) => {
    const params = item.formal_param_symbol_ids
    return params.length === symbolsById.get(item.source_symbol_id)?.arity
      && new Set(params).size === params.length
      && params.every((id) => symbolsById.get(id)?.symbol_type.name === SYMBOL_TYPE.freeTermVariable)
  })) return null

  return { term_substs, prop_substs }
}
