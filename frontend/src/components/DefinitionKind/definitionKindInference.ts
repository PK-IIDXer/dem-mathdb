import type { DefinitionCreateKind } from '../../api/types'
import { SYMBOL_TYPE } from '../../constants/symbolTypes'

export const DEFINITION_CREATE_KINDS = [
  'predicate',
  'function',
  'logical',
  'quant_prop',
  'quant_term',
] as const satisfies readonly DefinitionCreateKind[]

export interface DefinitionParamShape {
  symbolTypeName: string
  arity: number
}

export type DefinitionBodyType = 'proposition' | 'term'

/** Infers exactly the five definition kinds accepted by the REST API.
 * Descriptive functions are deliberately absent: function_desc requires a
 * proof-backed service path which the REST API does not expose. */
export function inferDefinitionKind(
  params: readonly DefinitionParamShape[],
  bodyType: DefinitionBodyType | null,
): DefinitionCreateKind | null {
  if (bodyType === null) return null
  if (params.every(({ symbolTypeName }) => symbolTypeName === SYMBOL_TYPE.freeTermVariable)) {
    return bodyType === 'proposition' ? 'predicate' : 'function'
  }
  if (params.length !== 1 || params[0].symbolTypeName !== SYMBOL_TYPE.freePropositionVariable) {
    return null
  }
  if (params[0].arity === 0 && bodyType === 'proposition') return 'logical'
  if (params[0].arity === 1) return bodyType === 'proposition' ? 'quant_prop' : 'quant_term'
  return null
}
