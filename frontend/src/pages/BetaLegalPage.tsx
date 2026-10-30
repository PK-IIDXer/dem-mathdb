import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { createElement } from 'react'
import { Link } from 'react-router-dom'
import { BETA_LEGAL_COPY } from './betaLegalCopy'
import { BETA_LEGAL_ESTABLISHED_DATE } from './legalDate'

export function BetaLegalPage({ kind }: { kind: keyof typeof BETA_LEGAL_COPY }) {
  const language = useLanguage()

  return <div className="space-y-8 text-sm text-slate-700">
    {language === 'en' && <p lang="en">{t('legalReference')}</p>}
    {(language === 'ja' ? ['ja', 'en'] as const : ['en'] as const).map(language => <section key={language} lang={language} className="space-y-4">
      {BETA_LEGAL_COPY[kind][language].map(([tag, text], index) => createElement(tag, {
        key: index, className: tag.startsWith('h') ? 'font-semibold text-slate-900' : undefined,
      }, text.replace('YYYY-MM-DD', BETA_LEGAL_ESTABLISHED_DATE)))}
    </section>)}
    <Link to="/contact" className="inline-block underline">{t("BetaLegalPage_542")}</Link>
  </div>
}
