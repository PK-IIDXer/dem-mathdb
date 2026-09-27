export type DefinitionFormulaSectionRole = 'readable' | 'axiom' | 'combined'

export interface DefinitionFormulaSection {
  formulaId: number
  role: DefinitionFormulaSectionRole
}

/**
 * Plans the formula previews on a definition page.  Function definitions use
 * the defining axiom itself as their readable formula, so equal ids must share
 * one preview (and therefore one KaTeX tree).
 */
export function buildDefinitionFormulaSections(
  displayFormulaId: number | null,
  axiomFormulaId: number | null,
): DefinitionFormulaSection[] {
  if (displayFormulaId !== null && displayFormulaId === axiomFormulaId) {
    return [{ formulaId: displayFormulaId, role: 'combined' }]
  }

  const sections: DefinitionFormulaSection[] = []
  if (displayFormulaId !== null) {
    sections.push({ formulaId: displayFormulaId, role: 'readable' })
  }
  if (axiomFormulaId !== null) {
    sections.push({ formulaId: axiomFormulaId, role: 'axiom' })
  }
  return sections
}
