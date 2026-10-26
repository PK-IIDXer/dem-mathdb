import { Link } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { proofsApi } from '../api/proofs'
import type { Theorem } from '../api/types'
import { useBeta } from './BetaContext'

export function BetaGettingStarted({ theorems }: { theorems: Theorem[] }) {
  const beta = useBeta()
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
  </section>
}
