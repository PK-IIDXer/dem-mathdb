export const ONBOARDING_TAG_NAME = 'system:onboarding'
export const ONBOARDING_FORMULA = 'forall x. P(x) -> P(x)'

export function onboardingQuery(extra: Record<string, string | number> = {}): string {
  const params = new URLSearchParams({ onboarding: '1' })
  for (const [key, value] of Object.entries(extra)) params.set(key, String(value))
  return `?${params}`
}
