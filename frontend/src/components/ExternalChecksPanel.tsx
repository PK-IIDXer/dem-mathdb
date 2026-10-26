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
      <h3 id="external-checks-heading" className="text-sm font-semibold text-slate-800">状態と外部の検査</h3>
      <p className="text-sm text-slate-700">
        <span className="font-semibold">DEM:</span>{' '}
        {theorem.status === 'proven' ? '証明済み' : '未証明（予想）'}
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
              {sourceLabel(check)} から翻訳。{passed ? '模型と逆翻訳を確認済み' : '翻訳の検査は未了'}
            </p>
            <dl className="grid grid-cols-[8rem_1fr] gap-x-2 gap-y-1 text-xs text-slate-600">
              <dt>出典</dt><dd>{check.file}:{check.line}（{check.module}）</dd>
              <dt>toolchain</dt><dd>{check.check_toolchain ?? '記録なし'}</dd>
              <dt>検査日時</dt><dd>{check.checked_at ?? '記録なし'}</dd>
              <dt>ライセンス</dt><dd>{check.license}</dd>
              <dt>著作権</dt><dd>{check.copyright ?? '記録なし'}</dd>
              <dt>著者</dt><dd>{check.authors ?? '記録なし'}</dd>
            </dl>
            <p className="rounded bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-900">
              DEM の式へ翻訳した改変物です。
            </p>

            {comparison && (
              <div className="space-y-2 rounded border border-violet-200 bg-violet-50 p-3" aria-label="Lean と DEM の公理依存の比較">
                <h4 className="font-semibold text-violet-900">公理依存の比較</h4>
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
                  <p className="text-xs font-semibold text-green-800">{comparison.dem_unused_axiom}を使いません。</p>
                )}
                <ul className="space-y-1 text-xs text-violet-900">
                  {comparisonSystems.map((system, index) => (
                    <li key={system.id}>
                      <SystemValidityNote namespace={system.namespace_name} />
                      {system.name}: {systemChecks[index]?.data == null ? '確認中…' : systemChecks[index].data.is_subset ? '真' : '偽'}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        )
      })}

      {checks.length === 0 && (
        <p className="text-xs text-slate-500">外部の検査記録はありません。</p>
      )}
    </section>
  )
}
