import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { configApi } from '../api/config'
import { axiomsApi } from '../api/axioms'
import { symbolsApi } from '../api/symbols'
import { useReadOnly } from '../ReadOnlyContext'
import { ONBOARDING_AXIOMS, onboardingAvailable, onboardingQuery } from '../onboarding'
import { Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import type { Theorem } from '../api/types'
import { useBeta } from './BetaContext'

export function BetaGettingStarted({ theorems }: { theorems: Theorem[] }) {
  useLanguage()

  const beta = useBeta()
  const readOnly = useReadOnly()
  const { isSuccess: configured } = useQuery({ queryKey: ['config'], queryFn: configApi.get, enabled: false })
  const writable = Boolean(configured && beta?.enabled && beta.write_state === 'open' && !readOnly)
  const prerequisites = useQuery({
    queryKey: ['onboarding', 'prerequisites', beta?.last_reset_at],
    queryFn: async () => {
      const [axioms, symbols, implication, universal] = await Promise.all([
        Promise.all(ONBOARDING_AXIOMS.map(name => axiomsApi.getByName(name))),
        symbolsApi.listSymbols(), symbolsApi.getByRole('implication'), symbolsApi.getByRole('universal_quantifier'),
      ])
      return onboardingAvailable(axioms, symbols, implication, universal)
    },
    enabled: writable, staleTime: 5 * 60_000, retry: false, refetchOnWindowFocus: false,
  })
  const candidates = theorems.filter(theorem => theorem.status === 'proven').slice(0, 3)
  const results = useQueries({ queries: candidates.map(theorem => ({ queryKey: ['theorems', theorem.id, 'proofs'], queryFn: () => proofsApi.listForTheorem(theorem.id), enabled: beta != null })) })
  if (!beta) return null
  const examples = candidates.flatMap((theorem, index) => {
    const proof = results[index].data?.find(proof => proof.status === 'verified')
    return proof ? [{ theorem, proof, path: `/theorems/${theorem.public_id}/proofs/${proof.public_id}` }] : []
  })
  const pending = results.some(result => result.isPending)
  const isError = results.some(result => result.isError)
  return <section aria-label={t("BetaGettingStarted_101")} className="space-y-2 rounded border border-indigo-200 bg-indigo-50 p-4 text-sm">
    <h2 className="font-semibold">{t("BetaGettingStarted_102")}</h2>
    <ol className="list-inside list-decimal space-y-2">
      <li><Link className="underline" to="/axioms">{t("BetaGettingStarted_103")}</Link></li>
      <li>{t("BetaGettingStarted_104")}{examples.map(({ theorem, proof, path }) => <Link key={proof.id} className="ml-2 underline" to={path}>{theorem.name}{t("BetaGettingStarted_105")}</Link>)}
        {!pending && !isError && !examples.length && <span>{t("BetaGettingStarted_106")}</span>}
        {isError && <span>{t("BetaGettingStarted_107")}<Link to="/proofs" className="underline">{t("BetaGettingStarted_108")}</Link></span>}
        {pending && <span>{t("BetaGettingStarted_109")}</span>}
      </li>
      <li>{examples[0] ? <Link className="underline" to={`${examples[0].path}#dependencies`}>{t("BetaGettingStarted_110")}</Link> : <Link className="underline" to="/proofs">{t("BetaGettingStarted_111")}</Link>}</li>
      <li><Link className="underline" to="/theorems">{t("BetaGettingStarted_112")}</Link></li>
    </ol>
    {writable && prerequisites.isSuccess && !prerequisites.isFetching && prerequisites.data === true && <section aria-label={t("BetaGettingStarted_113")} className="mt-3 border-t border-indigo-200 pt-3">
      <h3 className="font-semibold">{t("BetaGettingStarted_114")}</h3>
      <p>{t("BetaGettingStarted_115")}</p>
      <p>{t("BetaGettingStarted_116")}</p>
      <Link to={`/formulas${onboardingQuery()}`} className="mt-2 inline-block underline">{t("BetaGettingStarted_117")}</Link>
    </section>}
  </section>
}
