import { usePageTitle } from '../hooks/usePageTitle'
import { LEGAL_ESTABLISHED_DATE } from './legalDate'
import { useBeta } from '../components/BetaContext'
import { BetaLegalPage } from './BetaLegalPage'

export function TermsPage() {
  usePageTitle('利用規約')
  const beta = useBeta()
  if (beta) return <BetaLegalPage kind="terms" />
  return (
    <div className="space-y-8 text-sm text-slate-700">
      <section lang="ja" className="space-y-4">
        <h2 className="font-semibold text-slate-900">利用規約</h2>
        <p>この利用規約 (以下「本規約」) は、Deus Ex Machina (以下「本サイト」) の利用条件を定めるものです。本サイトを利用した時点で、本規約に同意したものとみなします。</p>
        <h3 className="font-semibold text-slate-900">1. 本サイトの内容</h3>
        <p>本サイトは、数学の記号・定義・公理・定理・証明と、その検証結果を閲覧できるサイトです。運営者は、予告なく本サイトの内容を変更し、または提供を中断・終了することがあります。</p>
        <h3 className="font-semibold text-slate-900">2. 禁止事項</h3>
        <p>本サイトの利用にあたり、次の行為を禁止します。</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>法令または公序良俗に反する行為</li>
          <li>本サイトのサーバーやネットワークに過度な負荷をかける行為 (短時間に大量のリクエストを送る自動取得を含みます)</li>
          <li>本サイトの運営を妨げる行為、不正にアクセスしようとする行為</li>
          <li>本サイトの内容を、法令で認められる範囲を超えて複製・転載・再配布する行為</li>
        </ul>
        <h3 className="font-semibold text-slate-900">3. 権利の帰属</h3>
        <p>本サイトのプログラム・文章・データに関する著作権その他の権利は、運営者または正当な権利者に帰属します。著作権法で認められる引用などの範囲を超えて利用することはできません。本サイトへのリンクは自由です。第三者のライセンスに基づく内容がある場合は、「出典とライセンス」のページに記載したとおりとします。</p>
        <h3 className="font-semibold text-slate-900">4. 免責</h3>
        <p>本サイトの内容と検証結果について、運営者は正確性・完全性・有用性を保証しません。詳しくは「免責事項」のページをご覧ください。本サイトの利用、または利用できなかったことによって生じた損害について、運営者は責任を負いません。</p>
        <h3 className="font-semibold text-slate-900">5. 本規約の変更</h3>
        <p>運営者は、必要に応じて本規約を変更することがあります。変更後の本規約は、本サイトに掲載した時点で効力を生じます。</p>
        <h3 className="font-semibold text-slate-900">6. 準拠法</h3>
        <p>本規約は日本法に準拠して解釈されます。</p>
        <p>本規約は日本語と英語で掲載しています。両者の内容が異なる場合は、日本語を優先します。</p>
        <p>制定日: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
      <section lang="en" className="space-y-4">
        <h2 className="text-base font-semibold text-slate-900">English</h2>
        <h3 className="font-semibold text-slate-900">Terms of Use</h3>
        <p>These Terms of Use ("Terms") set out the conditions for using Deus Ex Machina (the "Site"). By using the Site, you are deemed to have agreed to these Terms.</p>
        <h3 className="font-semibold text-slate-900">1. The Site</h3>
        <p>The Site lets you browse mathematical symbols, definitions, axioms, theorems and proofs, together with their verification results. The operator may change the Site, or suspend or discontinue it, at any time without notice.</p>
        <h3 className="font-semibold text-slate-900">2. Prohibited conduct</h3>
        <p>When using the Site, you must not:</p>
        <ul className="list-disc space-y-2 pl-6">
          <li>break the law or act against public order and morals;</li>
          <li>place an excessive load on the Site's servers or network (including automated retrieval that sends many requests in a short time);</li>
          <li>interfere with the operation of the Site or attempt unauthorized access;</li>
          <li>copy, republish or redistribute the Site's content beyond what the law permits.</li>
        </ul>
        <h3 className="font-semibold text-slate-900">3. Rights</h3>
        <p>Copyright and other rights in the Site's programs, text and data belong to the operator or to their rightful holders. You may not use them beyond what copyright law permits, such as quotation. You are free to link to the Site. Content provided under a third-party license, if any, is described on the "Sources and licenses" page.</p>
        <h3 className="font-semibold text-slate-900">4. Disclaimer</h3>
        <p>The operator makes no warranty as to the accuracy, completeness or usefulness of the Site's content or verification results. See the "Disclaimer" page for details. The operator is not liable for any damage arising from using, or being unable to use, the Site.</p>
        <h3 className="font-semibold text-slate-900">5. Changes to these Terms</h3>
        <p>The operator may change these Terms when necessary. Changes take effect when they are posted on the Site.</p>
        <h3 className="font-semibold text-slate-900">6. Governing law</h3>
        <p>These Terms are governed by the laws of Japan.</p>
        <p>These Terms are published in Japanese and English. If the two differ, the Japanese text prevails.</p>
        <p>Established: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
    </div>
  )
}
