import { usePageTitle } from '../hooks/usePageTitle'
import { LEGAL_ESTABLISHED_DATE } from './legalDate'
import { useBeta } from '../components/BetaContext'
import { BetaLegalPage } from './BetaLegalPage'

export function PrivacyPolicyPage() {
  usePageTitle('プライバシーポリシー')
  const beta = useBeta()
  if (beta) return <BetaLegalPage kind="privacy" />
  return (
    <div className="space-y-8 text-sm text-slate-700">
      <section lang="ja" className="space-y-4">
        <h2 className="font-semibold text-slate-900">プライバシーポリシー</h2>
        <h3 className="font-semibold text-slate-900">1. 取得する情報</h3>
        <p>本サイトには、利用者登録・ログイン・投稿・問い合わせフォームはありません。利用者から氏名・メールアドレスなどの個人情報を受け取る仕組みは持っていません。</p>
        <h3 className="font-semibold text-slate-900">2. アクセスログ</h3>
        <p>本サイトのサーバーは、運営・障害対応・不正利用の防止のため、アクセス日時・リクエストされた URL・接続元の IP アドレスなどを記録することがあります。記録は上記の目的に必要な期間 (原則として 30 日程度) 保存した後に削除し、法令に基づく場合を除いて第三者に提供しません。</p>
        <h3 className="font-semibold text-slate-900">3. Cookie・アクセス解析・広告</h3>
        <p>本サイトは現在、Cookie を使用するアクセス解析ツールや広告配信サービスを使用していません。今後導入する場合は、本ポリシーを改定して、その内容を明記します。</p>
        <h3 className="font-semibold text-slate-900">4. ブラウザへの保存</h3>
        <p>表示の設定 (表示密度など) は、利用者のブラウザの保存領域 (localStorage) に保存されます。この情報がサーバーへ送られることはありません。ブラウザの設定から削除できます。</p>
        <h3 className="font-semibold text-slate-900">5. 本ポリシーの変更</h3>
        <p>運営者は、必要に応じて本ポリシーを変更することがあります。変更後の本ポリシーは、本サイトに掲載した時点で効力を生じます。</p>
        <p>本ポリシーは日本語と英語で掲載しています。両者の内容が異なる場合は、日本語を優先します。</p>
        <p>制定日: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
      <section lang="en" className="space-y-4">
        <h2 className="text-base font-semibold text-slate-900">English</h2>
        <h3 className="font-semibold text-slate-900">Privacy Policy</h3>
        <h3 className="font-semibold text-slate-900">1. Information we collect</h3>
        <p>The Site has no user registration, login, posting or contact form. It has no means of receiving personal information such as names or email addresses from users.</p>
        <h3 className="font-semibold text-slate-900">2. Access logs</h3>
        <p>For operation, troubleshooting and preventing misuse, the Site's servers may record information such as the date and time of access, the requested URL and the client IP address. These records are kept only as long as needed for those purposes (in principle, about 30 days) and then deleted. They are not provided to third parties except as required by law.</p>
        <h3 className="font-semibold text-slate-900">3. Cookies, analytics and advertising</h3>
        <p>The Site currently uses no cookie-based analytics tools and no advertising services. If such tools are introduced in the future, this policy will be revised to describe them.</p>
        <h3 className="font-semibold text-slate-900">4. Data stored in your browser</h3>
        <p>Display settings (such as density) are stored in your browser's storage (localStorage). This information is not sent to the server. You can delete it through your browser settings.</p>
        <h3 className="font-semibold text-slate-900">5. Changes to this policy</h3>
        <p>The operator may change this policy when necessary. Changes take effect when they are posted on the Site.</p>
        <p>This policy is published in Japanese and English. If the two differ, the Japanese text prevails.</p>
        <p>Established: {LEGAL_ESTABLISHED_DATE}</p>
      </section>
    </div>
  )
}
