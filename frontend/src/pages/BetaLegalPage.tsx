import { createElement } from 'react'
import { Link } from 'react-router-dom'
import { BETA_LEGAL_COPY } from './betaLegalCopy'
import { BETA_LEGAL_ESTABLISHED_DATE } from './legalDate'

export function BetaLegalPage({ kind }: { kind: keyof typeof BETA_LEGAL_COPY }) {
  return <div className="space-y-8 text-sm text-slate-700">
    {(['ja', 'en'] as const).map(language => <section key={language} lang={language} className="space-y-4">
      {BETA_LEGAL_COPY[kind][language].map(([tag, text], index) => createElement(tag, {
        key: index, className: tag.startsWith('h') ? 'font-semibold text-slate-900' : undefined,
      }, text.replace('YYYY-MM-DD', BETA_LEGAL_ESTABLISHED_DATE)))}
    </section>)}
    <Link to="/contact" className="inline-block underline">お問い合わせ・削除依頼 / Contact and removal requests</Link>
  </div>
}
