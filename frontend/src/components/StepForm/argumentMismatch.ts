import { ApiError } from '../../api/client'
import type { Token } from '../../api/types'

export interface ArgumentMismatch {
  premise: number
  expected?: Token[]
  actual?: Token[]
}

export function argumentMismatch(error: unknown): ArgumentMismatch | null {
  if (!(error instanceof ApiError) || !error.body || typeof error.body !== 'object') return null
  const body = error.body as {
    code?: string
    details?: { arg_index?: number; expected?: { tokens?: Token[] }; actual?: { tokens?: Token[] } }
  }
  if (body.code !== 'proof.arg_mismatch' || typeof body.details?.arg_index !== 'number') return null
  return {
    premise: body.details.arg_index + 1,
    expected: body.details.expected?.tokens,
    actual: body.details.actual?.tokens,
  }
}
