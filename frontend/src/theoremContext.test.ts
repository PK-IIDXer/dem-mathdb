import { describe, expect, it } from 'vitest'
import { theoremVariableContext } from './theoremContext'

describe('theoremVariableContext', () => {
  it('reads Phase 1 declarations and rejects unrelated or malformed remarks', () => {
    expect(theoremVariableContext('{"phase1":{"variables":{"x":12,"y":13}}}')).toEqual({ x: 12, y: 13 })
    expect(theoremVariableContext('{"phase1":{"variables":{"x":"12"}}}')).toEqual({})
    expect(theoremVariableContext('ordinary prose')).toEqual({})
    expect(theoremVariableContext(null)).toEqual({})
  })
})
