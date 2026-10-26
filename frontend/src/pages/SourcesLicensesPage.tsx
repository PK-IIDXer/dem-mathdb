import { usePageTitle } from '../hooks/usePageTitle'
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import apacheLicense from '../content/apache-2.0.txt?raw'

export function SourcesLicensesPage() {
  usePageTitle('出典とライセンス')
  const { data: sources = [] } = useQuery({
    queryKey: ['externalSources'],
    queryFn: () => theoremsApi.listExternalSources(),
  })

  return (
    <div className="space-y-6 text-sm text-slate-700">
      <div>
        <h2 className="text-base font-semibold text-slate-900">出典とライセンス</h2>
        <p className="mt-2">
          外部ライブラリから取り込んだ文は、出典・検査記録・DEM の式へ翻訳した改変物であることを定理ごとに表示します。
        </p>
      </div>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-900">取り込んだライブラリ</h3>
        {sources.map((source) => (
          <article key={`${source.library_commit}:${source.library}`} className="rounded border border-slate-200 p-3">
            <p className="font-semibold">
              {source.library === 'mathlib' ? 'Mathlib' : source.library === 'lean' ? 'Lean' : source.library}{' '}
              {source.library_version}
            </p>
            <p className="font-mono text-xs text-slate-500">{source.library_commit}</p>
            <p>{source.imported_statements} 文 ／ {source.license}</p>
            <p className="text-xs text-slate-500">
              NOTICE: {source.notice_status === 'absent' ? 'この版にはありません（版を上げる際に再確認）' : source.notice_status === 'present' ? 'あり' : '未確認'}
            </p>
          </article>
        ))}
        {sources.length === 0 && <p className="text-slate-500">外部から取り込んだ文はありません。</p>}
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-900">Apache License 2.0 全文</h3>
        <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-4 text-xs">
          {apacheLicense}
        </pre>
      </section>
    </div>
  )
}
