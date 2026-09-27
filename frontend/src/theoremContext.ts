export function theoremVariableContext(remarks: string | null): Record<string, number> {
  if (!remarks) return {}
  try {
    const parsed = JSON.parse(remarks) as { phase1?: { variables?: unknown } }
    const variables = parsed.phase1?.variables
    if (!variables || typeof variables !== 'object' || Array.isArray(variables)) return {}
    return Object.fromEntries(
      Object.entries(variables).filter(
        (entry): entry is [string, number] => Boolean(entry[0]) && Number.isInteger(entry[1]),
      ),
    )
  } catch {
    return {}
  }
}
