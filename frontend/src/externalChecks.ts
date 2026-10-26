import type { AxiomSystem, ExternalCheck, Theorem } from './api/types'

export function externalCheckPassed(check: ExternalCheck): boolean {
  return check.check_model === 'passed' && check.check_roundtrip === 'passed'
}

// The default "valid in which system" comparison is foundation data
// (axiom_system.comparison_rank, set by the seed), not a list of names here.
// scripts/public_api_data.py applies the same rule to capture these requests.
export function comparisonSystems(systems: AxiomSystem[]): AxiomSystem[] {
  return systems
    .filter((system) => system.comparison_rank != null)
    .sort((a, b) => (a.comparison_rank as number) - (b.comparison_rank as number))
}

export function hasPassedExternalCheck(theorem: Theorem): boolean {
  return (theorem.external_checks ?? []).some(externalCheckPassed)
}

export function theoremValidationCounts(theorems: Theorem[]) {
  return {
    total: theorems.length,
    demProven: theorems.filter((theorem) => theorem.status === 'proven').length,
    leanOnly: theorems.filter(
      (theorem) => theorem.status !== 'proven' && hasPassedExternalCheck(theorem),
    ).length,
  }
}
