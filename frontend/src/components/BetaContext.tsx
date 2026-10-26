import { createContext, useContext } from 'react'
import type { BetaConfig } from '../api/config'

export const BetaContext = createContext<BetaConfig | null>(null)
export const useBeta = () => useContext(BetaContext)

export const MAINTENANCE = 'メンテナンス中のため、書き込みを止めています。少し待って再読み込みしてください。'
export const FULL = '容量の上限に達したため、次のリセットまで書き込めません。'
export function localTime(value: string | null): string {
  if (!value || Number.isNaN(Date.parse(value))) return '未定'
  return new Date(value).toLocaleString()
}
