import { usePageTitle } from '../hooks/usePageTitle'
import { LEGAL_ESTABLISHED_DATE } from './legalDate'
import { useBeta } from '../components/BetaContext'
import { BetaLegalPage } from './BetaLegalPage'

export function DisclaimerPage() {
  usePageTitle('免責事項')
  const beta = useBeta()
  if (beta) return <BetaLegalPage kind="disclaimer" />
  return (
    <div className="space-y-8 text-sm text-slate-700">
      <section lang="ja" className="space-y-4">
        <h2 className="font-semibold text-slate-900">免責事項</h2>
        <h3 className="font-semibold text-slate-900">1. 内容と検証結果について</h3>
        <p>本サイトに掲載する証明は、本サイトの検証プログラムによって機械的に検査されています。ただし、検証プログラム、記号の定義、公理の選び方、データの入力に誤りがある可能性は否定できません。運営者は、掲載する内容と検証結果の正確性・完全性・有用性を保証しません。</p>
        <h3 className="font-semibold text-slate-900">2. 損害について</h3>
        <p>本サイトの利用、または利用できなかったことによって生じた損害について、運営者は責任を負いません。</p>
        <h3 className="font-semibold text-slate-900">3. 外部リンクについて</h3>
        <p>本サイトから外部サイトへリンクすることがあります。リンク先の内容について、運営者は責任を負いません。</p>
        <p>本ページは日本語と英語で掲載しています。両者の内容が異なる場合は、日本語を優先します。</p>
        <p>制定日: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
      <section lang="en" className="space-y-4">
        <h2 className="text-base font-semibold text-slate-900">English</h2>
        <h3 className="font-semibold text-slate-900">Disclaimer</h3>
        <h3 className="font-semibold text-slate-900">1. Content and verification results</h3>
        <p>The proofs on the Site are checked mechanically by the Site's verification program. Errors in the verification program, in the definitions of symbols, in the choice of axioms or in the data entry cannot be ruled out. The operator makes no warranty as to the accuracy, completeness or usefulness of the content or the verification results.</p>
        <h3 className="font-semibold text-slate-900">2. Damages</h3>
        <p>The operator is not liable for any damage arising from using, or being unable to use, the Site.</p>
        <h3 className="font-semibold text-slate-900">3. External links</h3>
        <p>The Site may link to external websites. The operator is not responsible for the content of linked sites.</p>
        <p>This page is published in Japanese and English. If the two differ, the Japanese text prevails.</p>
        <p>Established: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
    </div>
  )
}
