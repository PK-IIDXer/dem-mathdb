import type { Axiom, Symbol } from './api/types'
import { SYMBOL_TYPE } from './constants/symbolTypes'

export const ONBOARDING_TAG_NAME = 'system:onboarding'
export const ONBOARDING_FORMULA = 'forall x. P(x) -> P(x)'

export function onboardingQuery(extra: Record<string, string | number> = {}): string {
  const params = new URLSearchParams({ onboarding: '1' })
  for (const [key, value] of Object.entries(extra)) params.set(key, String(value))
  return `?${params}`
}

// Existing script names, shared by the flow and its opt-in prerequisite check.
export const ONBOARDING_AXIOMS = ['hilbert_k', 'hilbert_s'] as const
export const ONBOARDING_PREDICATE = 'φ¹'

export function findOnboardingPredicate(symbols: Symbol[]): Symbol | undefined {
  return symbols.find(symbol => symbol.name === ONBOARDING_PREDICATE && symbol.arity === 1 && symbol.symbol_type.name === SYMBOL_TYPE.freePropositionVariable)
}

export function onboardingAvailable(axioms: Axiom[], symbols: Symbol[], implication: Symbol, universal: Symbol): boolean {
  return axioms.length === ONBOARDING_AXIOMS.length && axioms.every(axiom => axiom.id > 0 && axiom.formula_id > 0)
    && Boolean(findOnboardingPredicate(symbols))
    && symbols.some(symbol => symbol.arity === 0 && symbol.symbol_type.name === SYMBOL_TYPE.freeTermVariable)
    && symbols.some(symbol => symbol.id === implication.id) && implication.arity === 2
    && symbols.some(symbol => symbol.id === universal.id) && universal.symbol_type.is_quantifier
}
