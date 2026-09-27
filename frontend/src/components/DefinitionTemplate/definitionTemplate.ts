export type DefinitionTemplateMode = 'as-is' | 'is-has' | 'custom'

export interface DefinitionTemplateRecord {
  name: string
  latex_template: string | null
}

function displayBaseName(name: string): string {
  return name.trim().replace(/\[[^\]]+\]$/, '')
}

function statementName(baseName: string): string {
  if (baseName.startsWith('Is') || baseName.startsWith('Has')) return baseName
  if (baseName.endsWith('UniversalProperty') || baseName === 'EpiMonicFactorization') {
    return `Has${baseName}`
  }
  return `Is${baseName}`
}

export function definitionTemplateChoices(name: string): {
  asIs: string
  isHas: string
  isHasPrefix: 'Is' | 'Has'
} {
  const asIs = name.trim() || '\\square'
  const statement = statementName(displayBaseName(name) || '?')
  return {
    asIs,
    isHas: `\\mathsf{${statement}}`,
    isHasPrefix: statement.startsWith('Has') ? 'Has' : 'Is',
  }
}

export function classifyDefinitionTemplate(
  symbol: DefinitionTemplateRecord,
): DefinitionTemplateMode {
  const template = symbol.latex_template?.trim() || symbol.name
  if (template === symbol.name) return 'as-is'
  if (/^\\mathsf\{(?:Is|Has)[^{}]+\}$/.test(template)) return 'is-has'
  return 'custom'
}
