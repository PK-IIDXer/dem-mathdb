import { useBeta, localTime, MAINTENANCE, FULL } from './BetaContext'
import { Link } from 'react-router-dom'

export function BetaBanner() {
  const beta = useBeta()
  if (!beta) return null
  return <aside aria-label="匿名公開β" className="mb-4 space-y-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
    <p>β 版です。データは予告なく消えます（定期的に初期状態へ戻します）。次回の予定: {localTime(beta.next_reset_at)}</p>
    <p lang="en">Public beta. Data may disappear without notice and is reset periodically. Next reset: {localTime(beta.next_reset_at)}</p>
    <Link to="/contact" className="inline-block underline">お問い合わせ・削除依頼</Link>
    {beta.write_state === 'maintenance' && <p>{MAINTENANCE}</p>}
    {beta.write_state === 'full' && <p>{FULL}</p>}
    {beta.write_state !== 'open' && <p lang="en">{beta.write_state === 'full' ? 'Storage is full. Writing resumes after a reset.' : 'Maintenance: writing is paused. Please try again later.'}</p>}
    {beta.last_reset_error && <div role="status">
      <p>前回の定期リセットが完了しませんでした（{localTime(beta.last_reset_error.failed_at)}）。データが予定どおり戻っていない場合があります。</p>
      <p lang="en">The last reset did not complete ({localTime(beta.last_reset_error.failed_at)}). Data may not have been reset as scheduled.</p>
    </div>}
  </aside>
}
