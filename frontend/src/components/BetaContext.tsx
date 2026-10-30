import { locale } from '../i18n/language'
import { t } from "../i18n/translate"
import { createContext, useContext } from 'react'
import type { BetaConfig } from '../api/config'

export const BetaContext = createContext<BetaConfig | null>(null)
export const useBeta = () => useContext(BetaContext)

export const MAINTENANCE = t("errorGuidance_021")
export const FULL = t("errorGuidance_022")
export function localTime(value: string | null): string {
  if (!value || Number.isNaN(Date.parse(value))) return t("BetaContext_100")
  return new Date(value).toLocaleString(locale())
}
