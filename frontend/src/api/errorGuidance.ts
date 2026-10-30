import { t } from "../i18n/translate"
export function retrySeconds(value: string | null): number | null {
  if (value == null || value.trim() === '') return null
  const seconds = /^\d+$/.test(value) ? Number(value) : Math.ceil((Date.parse(value) - Date.now()) / 1000)
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null
}

export function errorGuidance(status: number, body: unknown, retry: number | null): string | null {
  const data = body && typeof body === 'object' ? body as Record<string, unknown> : null
  const code = data?.code
  if (code === 'beta.contact_unavailable') return t("errorGuidance_000")
  if (code === 'beta.contact_invalid') return t("errorGuidance_001")
  if (code === 'beta.rate_limited' || code === 'beta.busy') return t("errorGuidance_002") + (retry == null ? t("errorGuidance_003") : t("errorGuidance_004", retry))
  if (code === 'beta.body_too_large' || (status === 413 && data == null)) return t("errorGuidance_005")
  if (code === 'beta.limit_exceeded') {
    const labels: Record<string, string> = { name: t("errorGuidance_006"), alias: t("errorGuidance_007"), title: t("errorGuidance_006"), description: t("errorGuidance_009"), remarks: t("errorGuidance_009"), notation: t("errorGuidance_011"), latex_template: t("errorGuidance_011"), formula_tokens: t("errorGuidance_013"), proof_steps: t("errorGuidance_014"), theorem_premises: t("errorGuidance_015") }
    const label = typeof data?.limit === 'string' ? labels[data.limit] ?? t("errorGuidance_016") : t("errorGuidance_016")
    const maximum = typeof data?.maximum === 'number' ? t("errorGuidance_018", data.maximum) : ''
    return t("errorGuidance_019", label, maximum)
  }
  if (code === 'formula.too_deep') return t("errorGuidance_020")
  if (code === 'beta.maintenance') return t("errorGuidance_021")
  if (code === 'beta.full') return t("errorGuidance_022")
  if (code === 'beta.disabled') return t("errorGuidance_023")
  if (code === 'db.guard_rejected') return t("errorGuidance_024")
  if ((status === 502 || status === 503) && data == null) return t("errorGuidance_025")
  return null
}
