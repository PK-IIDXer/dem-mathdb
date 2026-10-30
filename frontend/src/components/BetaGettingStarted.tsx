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
  return <section aria-label="βの道案内" className="space-y-2 rounded border border-indigo-200 bg-indigo-50 p-4 text-sm">
    <h2 className="font-semibold">共有 β の使い方</h2>
    <ol className="list-inside list-decimal space-y-2">
      <li><Link className="underline" to="/axioms">公理系を見る</Link></li>
      <li>証明済みの定理の証明を見る（step・カーネルの検証結果・使った公理）。
        {examples.map(({ theorem, proof, path }) => <Link key={proof.id} className="ml-2 underline" to={path}>{theorem.name}の証明</Link>)}
        {!pending && !isError && !examples.length && <span>まだありません。自分で定理を作れます。</span>}
        {isError && <span>証明を取得できませんでした。<Link to="/proofs" className="underline">証明一覧を開く</Link></span>}
        {pending && <span>読み込み中…</span>}
      </li>
      <li>{examples[0] ? <Link className="underline" to={`${examples[0].path}#dependencies`}>依存関係を見る</Link> : <Link className="underline" to="/proofs">依存関係は、証明ができたら証明の詳細で確認できます。</Link>}</li>
      <li><Link className="underline" to="/theorems">自分で定理を登録して証明する</Link></li>
    </ol>
    {writable && prerequisites.isSuccess && !prerequisites.isFetching && prerequisites.data === true && <section aria-label="βのチュートリアル" className="mt-3 border-t border-indigo-200 pt-3">
      <h3 className="font-semibold">はじめての方へ: 5 分で定理を証明してみよう</h3>
      <p>実際の画面を操作しながら、定理の登録から機械検証済みの証明までを体験できます。</p>
      <p>練習の定理は共有データベースに保存されますが、通常の定理一覧・検索・候補には表示しません。数式と直接 URL は共有されます。毎週月曜 4:00（日本時間）のリセットで消えます。</p>
      <Link to={`/formulas${onboardingQuery()}`} className="mt-2 inline-block underline">チュートリアルを始める</Link>
    </section>}
  </section>
}
