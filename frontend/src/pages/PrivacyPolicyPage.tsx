export function PrivacyPolicyPage() {
  return (
    <div className="space-y-4 text-sm text-slate-700">
      <h2 className="text-base font-semibold text-slate-900">プライバシーポリシー</h2>

      <p>
        Deus Ex Machina (以下「本サイト」) における個人情報およびアクセス情報の取り扱いについて、以下のとおり定めます。
      </p>

      <h3 className="text-sm font-semibold text-slate-900">アクセスログについて</h3>
      <p>
        サーバーの安全な運用と障害調査のため、リクエスト時刻、参照元、ブラウザ情報、IPアドレスなどのアクセスログが記録される場合があります。公開版には広告配信コードや第三者アクセス解析コードを含みません。
      </p>

      <h3 className="text-sm font-semibold text-slate-900">個人情報の取り扱い</h3>
      <p>
        本サイトでは、問い合わせ等で取得した個人情報を、その対応に必要な範囲で取り扱います。本ページは公開用の雛形であり、運営主体、問い合わせ先、保存期間、適用法令に関する具体的な情報は、実際に運営されるサイトの方針に基づいて定められます。
      </p>

      <h3 className="text-sm font-semibold text-slate-900">免責事項</h3>
      <p>
        本サイトに掲載する情報の正確性には注意を払っていますが、内容を保証するものではありません。本サイトの利用によって生じた損害について、一切の責任を負いません。詳細は
        <a className="text-indigo-600 hover:underline" href="/disclaimer">
          免責事項
        </a>
        ページをご覧ください。
      </p>

      <h3 className="text-sm font-semibold text-slate-900">プライバシーポリシーの変更について</h3>
      <p>本サイトは、内容を予告なく変更することがあります。変更後のプライバシーポリシーは、本ページに掲載した時点で効力を生じるものとします。</p>
    </div>
  )
}
