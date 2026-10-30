import { createElement } from 'react'
import { t } from '../i18n/translate'
import { useLanguage } from '../i18n/useLanguage'
import { LEGAL_COPY, type LegalRow } from './legalCopy'
import { LEGAL_ESTABLISHED_DATE } from './legalDate'

export function StandardLegalPage({ kind }: { kind: keyof typeof LEGAL_COPY }) {
  const language = useLanguage()
  return <div className="space-y-8 text-sm text-slate-700">
    {language === 'ja' && section('ja')}
    {language === 'en' && <p lang="en">{t('legalReference')}</p>}
    {section('en')}
  </div>

  function section(language: 'ja' | 'en') {
    const rows: readonly LegalRow[] = LEGAL_COPY[kind][language]
    return <section lang={language} className="space-y-4">
      {rows.map(([tag, text], index) => tag === 'ul'
        ? <ul key={index} className="list-disc space-y-2 pl-6">{text.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul>
        : createElement(tag, {
          key: index,
          className: tag === 'h2' && language === 'en' ? 'text-base font-semibold text-slate-900'
            : tag.startsWith('h') ? 'font-semibold text-slate-900' : undefined,
        }, text.replace('YYYY-MM-DD', LEGAL_ESTABLISHED_DATE)))}
    </section>
  }
}
