import type { Token, Symbol } from '../api/types'

export function entityOrigin(namespace: string | undefined, local: string | undefined): 'user' | 'base' | null {
  return namespace == null || local == null ? null : namespace === local ? 'user' : 'base'
}

export function hasUserSymbols(tokens: Token[], symbols: Symbol[], local: string | undefined): boolean {
  if (local == null) return false
  const userIds = new Set(symbols.filter(symbol => symbol.namespace_name === local).map(symbol => symbol.id))
  return tokens.some(token => token.symbol_id != null && userIds.has(token.symbol_id))
}
