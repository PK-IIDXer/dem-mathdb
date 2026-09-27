import type { Symbol } from '../../api/types'

/** Apply theorem-local declaration names only while rendering a formula.
 * Formula trees must still be parsed with the original symbol metadata so
 * arity and notation stay independent from the display context. */
export function symbolsWithDeclarationNames(
  symbolsById: Map<number, Symbol>,
  context: Record<string, number>,
): Map<number, Symbol> {
  const declarationsById = new Map(Object.entries(context).map(([name, id]) => [id, name]))
  return new Map([...symbolsById].map(([id, symbol]) => {
    const declarationName = declarationsById.get(id)
    return [
      id,
      declarationName
        ? { ...symbol, name: declarationName, latex_template: declarationName }
        : symbol,
    ]
  }))
}
