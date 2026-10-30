import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useBeta, localTime } from './BetaContext'
import { Link } from 'react-router-dom'

export function BetaBanner() {
  const language = useLanguage()

  const beta = useBeta()
  if (!beta) return null
  return <aside aria-label={t("BetaBanner_093")} className="mb-4 space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
    <p>{t("BetaBanner_094")}{localTime(beta.next_reset_at)}</p>
    {language === 'ja' && <p lang="en">Public beta. Data may disappear without notice and is reset periodically. Next reset: {localTime(beta.next_reset_at)}</p>}
    <Link to="/contact" className="inline-block underline">{t("App_031")}</Link>
    {beta.write_state === 'maintenance' && <p>{t("errorGuidance_021")}</p>}
    {beta.write_state === 'full' && <p>{t("errorGuidance_022")}</p>}
    {language === 'ja' && beta.write_state !== 'open' && <p lang="en">{beta.write_state === 'full' ? 'Storage is full. Writing resumes after a reset.' : 'Maintenance: writing is paused. Please try again later.'}</p>}
    {beta.last_reset_error && <div role="status">
      <p>{t("BetaBanner_096")}{localTime(beta.last_reset_error.failed_at)}{t("BetaBanner_097")}</p>
      {language === 'ja' && <p lang="en">The last reset did not complete ({localTime(beta.last_reset_error.failed_at)}). Data may not have been reset as scheduled.</p>}
    </div>}
  </aside>
}
