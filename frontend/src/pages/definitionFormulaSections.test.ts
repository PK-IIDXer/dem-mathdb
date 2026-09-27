import { describe, expect, it } from 'vitest'
import { buildDefinitionFormulaSections } from './definitionFormulaSections'

describe('buildDefinitionFormulaSections', () => {
  it('shares one preview when the readable formula is the defining axiom', () => {
    expect(buildDefinitionFormulaSections(17, 17)).toEqual([{ formulaId: 17, role: 'combined' }])
  })

  it('keeps distinct readable and axiom formulas', () => {
    expect(buildDefinitionFormulaSections(17, 18)).toEqual([
      { formulaId: 17, role: 'readable' },
      { formulaId: 18, role: 'axiom' },
    ])
  })

  it('keeps a readable formula without an axiom', () => {
    expect(buildDefinitionFormulaSections(17, null)).toEqual([{ formulaId: 17, role: 'readable' }])
  })

  it('keeps an axiom formula without a readable formula', () => {
    expect(buildDefinitionFormulaSections(null, 18)).toEqual([{ formulaId: 18, role: 'axiom' }])
  })
})
