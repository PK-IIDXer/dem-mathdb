import { describe, expect, it } from 'vitest'
import { ONBOARDING_FORMULA, onboardingQuery } from './onboarding'

describe('onboarding', () => {
  it('uses the specified formula and preserves navigation parameters', () => {
    expect(ONBOARDING_FORMULA).toBe('forall x. P(x) -> P(x)')
    expect(onboardingQuery({ theorem_id: 5 })).toBe('?onboarding=1&theorem_id=5')
  })
})
