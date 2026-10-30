import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { SystemValidityNote } from './BetaIdentity'
import { useQueries, useQuery } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'
import { proofsApi } from '../api/proofs'
import type { ExternalCheck, Theorem } from '../api/types'
import { comparisonSystems as selectComparisonSystems, externalCheckPassed } from '../externalChecks'

function sourceLabel(check: ExternalCheck) {
  const library = check.library === 'mathlib' ? 'Mathlib' : check.library === 'lean' ? 'Lean' : check.library
  return `${library} ${check.library_version} ${check.declaration}`
}

export function ExternalChecksPanel({
  theorem,
  verifiedProofId,
}: {
  theorem: Theorem
  verifiedProofId: number | null
}) {
  useLanguage()

  const checks = theorem.external_checks ?? []
  const { data: usedAxioms = [] } = useQuery({
    queryKey: ['proofs', verifiedProofId, 'used-axioms'],
    queryFn: () => proofsApi.listUsedAxioms(verifiedProofId as number),
    enabled: verifiedProofId != null && checks.length > 0,
  })
  const { data: systems = [] } = useQuery({
    queryKey: ['axiomSystems'],
    queryFn: () => axiomsApi.listSystems(),
    enabled: verifiedProofId != null && checks.length > 0,
  })
  const comparisonSystems = selectComparisonSystems(systems)
  const systemChecks = useQueries({
    queries: comparisonSystems.map((system) => ({
      queryKey: ['proofs', verifiedProofId, 'valid-in-system', system.id],
      queryFn: () => proofsApi.isValidInSystem(verifiedProofId as number, system.id),
      enabled: verifiedProofId != null,
    })),
  })

  return (
    <section aria-labelledby="external-checks-heading" className="space-y-3 rounded border border-slate-200 bg-slate-50 p-3">
      <h3 id="external-checks-heading" className="text-sm font-semibold text-slate-800">{t("ExternalChecksPanel_139")}</h3>
      <p className="text-sm text-slate-700">
        <span className="font-semibold">DEM:</span>{' '}
        {theorem.status === 'proven' ? t("DependencyGraph_126") : t("ExternalChecksPanel_141")}
      </p>

      {checks.map((check) => {
        const passed = externalCheckPassed(check)
        // Which statements get a comparison, and its wording, are the
        // foundation's data on the import record (public-phase1 §15).
        const comparison = verifiedProofId != null ? check.axiom_comparison : null
        return (
          <article key={`${check.library_commit}:${check.declaration}`} className="space-y-2 rounded border border-indigo-100 bg-white p-3 text-sm">
            <p>
              <span className="font-semibold">Lean:</span>{' '}
              {sourceLabel(check)} {t("ExternalChecksPanel_142")}{passed ? t("ExternalChecksPanel_143") : t("ExternalChecksPanel_144")}
            </p>
            <dl className="grid grid-cols-[8rem_1fr] gap-x-2 gap-y-1 text-xs text-slate-600">
              <dt>{t("ExternalChecksPanel_145")}</dt><dd>{check.file}:{check.line}（{check.module}）</dd>
              <dt>toolchain</dt><dd>{check.check_toolchain ?? t("ExternalChecksPanel_146")}</dd>
              <dt>{t("ExternalChecksPanel_147")}</dt><dd>{check.checked_at ?? t("ExternalChecksPanel_146")}</dd>
              <dt>{t("ExternalChecksPanel_149")}</dt><dd>{check.license}</dd>
              <dt>{t("ExternalChecksPanel_150")}</dt><dd>{check.copyright ?? t("ExternalChecksPanel_146")}</dd>
              <dt>{t("ExternalChecksPanel_152")}</dt><dd>{check.authors ?? t("ExternalChecksPanel_146")}</dd>
            </dl>
            <p className="rounded bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-900">
              {t("ExternalChecksPanel_154")}</p>

            {comparison && (
              <div className="space-y-2 rounded border border-violet-200 bg-violet-50 p-3" aria-label={t("ExternalChecksPanel_155")}>
                <h4 className="font-semibold text-violet-900">{t("ExternalChecksPanel_156")}</h4>
                <p>
                  <span className="font-semibold">Lean:</span> {comparison.lean}
                  {check.source_axioms.includes(comparison.lean_axiom) && `（${comparison.lean_axiom}。${comparison.lean_axiom_note}）`}
                </p>
                <p className="text-xs text-violet-800">{check.source_axioms.join('、')}</p>
                <p>
                  <span className="font-semibold">DEM:</span> {comparison.dem}
                  {usedAxioms.length > 0 && `（${usedAxioms.map((axiom) => axiom.name).join('、')}）`}
                </p>
                {!usedAxioms.some((axiom) => axiom.name === comparison.dem_unused_axiom) && (
                  <p className="text-xs font-semibold text-green-800">{comparison.dem_unused_axiom}{t("ExternalChecksPanel_157")}</p>
                )}
                <ul className="space-y-1 text-xs text-violet-900">
                  {comparisonSystems.map((system, index) => (
                    <li key={system.id}>
                      <SystemValidityNote namespace={system.namespace_name} />
                      {system.name}: {systemChecks[index]?.data == null ? t("ExternalChecksPanel_158") : systemChecks[index].data.is_subset ? t("ExternalChecksPanel_159") : t("ExternalChecksPanel_160")}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        )
      })}

      {checks.length === 0 && (
        <p className="text-xs text-slate-500">{t("ExternalChecksPanel_161")}</p>
      )}
    </section>
  )
}
