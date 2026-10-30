import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { usePageTitle } from '../hooks/usePageTitle'
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import apacheLicense from '../content/apache-2.0.txt?raw'

export function SourcesLicensesPage() {
  useLanguage()

  usePageTitle(t("App_035"))
  const { data: sources = [] } = useQuery({
    queryKey: ['externalSources'],
    queryFn: () => theoremsApi.listExternalSources(),
  })

  return (
    <div className="space-y-6 text-sm text-slate-700">
      <div>
        <h2 className="text-base font-semibold text-slate-900">{t("App_035")}</h2>
        <p className="mt-2">
          {t("SourcesLicensesPage_706")}</p>
      </div>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-900">{t("SourcesLicensesPage_707")}</h3>
        {sources.map((source) => (
          <article key={`${source.library_commit}:${source.library}`} className="rounded border border-slate-200 p-3">
            <p className="font-semibold">
              {source.library === 'mathlib' ? 'Mathlib' : source.library === 'lean' ? 'Lean' : source.library}{' '}
              {source.library_version}
            </p>
            <p className="font-mono text-xs text-slate-500">{source.library_commit}</p>
            <p>{source.imported_statements} {t("SourcesLicensesPage_708")}{source.license}</p>
            <p className="text-xs text-slate-500">
              NOTICE: {source.notice_status === 'absent' ? t("SourcesLicensesPage_709") : source.notice_status === 'present' ? t("SourcesLicensesPage_710") : t("SourcesLicensesPage_711")}
            </p>
          </article>
        ))}
        {sources.length === 0 && <p className="text-slate-500">{t("SourcesLicensesPage_712")}</p>}
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold text-slate-900">{t("SourcesLicensesPage_713")}</h3>
        <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-4 text-xs">
          {apacheLicense}
        </pre>
      </section>
    </div>
  )
}
