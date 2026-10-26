import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useBeta } from '../components/BetaContext'
import { usePageTitle } from '../hooks/usePageTitle'

export function ContactPage() {
  usePageTitle('お問い合わせ・削除依頼')
  const beta = useBeta()
  const [kind, setKind] = useState('other')
  const [target, setTarget] = useState('')
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!beta) return <p>ページが見つかりません。</p>

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!message.trim() || message.length > 2000 || target.length > 500 || reply.length > 254 ||
        (target !== '' && !/^(https?:\/\/|\/)/.test(target))) {
      setError('入力内容を確認してください。本文は1〜2,000文字、対象URLは500文字、返信先は254文字までです。URLは http://、https://、/ のいずれかで始めてください。')
      return
    }
    setSending(true)
    try {
      await api.post('/contact', { kind, target_url: target || null, message, reply_to: reply || null })
      setAccepted(true)
      setMessage('')
      setReply('')
      setTarget('')
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : '通信できませんでした。接続を確認して再試行してください。')
    } finally {
      setSending(false)
    }
  }

  return <div className="max-w-2xl space-y-4 text-sm text-slate-700">
    <h2 className="text-lg font-semibold">お問い合わせ・削除依頼</h2>
    <p>個人情報や秘密の情報を本文に書かないでください。返信先は任意です。問い合わせの本文は通知のためSlackへ送ります。</p>
    {accepted ? <p role="status">受け付けました。個別の返信はお約束できません。</p> : <form onSubmit={submit} className="space-y-4">
      <label className="block">種別
        <select value={kind} onChange={event => setKind(event.target.value)} className="ml-2 rounded border p-2">
          <option value="removal">削除依頼</option><option value="bug">不具合</option><option value="other">その他</option>
        </select>
      </label>
      {kind === 'removal' && <p>削除依頼では、対象の頁のURLを入力してください。分からない場合は本文で対象を説明してください。</p>}
      <label className="block">対象の頁のURL（任意・500文字まで）
        <input value={target} onChange={event => setTarget(event.target.value)} maxLength={500} className="mt-1 block w-full rounded border p-2" />
      </label>
      <label className="block">本文（必須・2,000文字まで）
        <textarea value={message} onChange={event => setMessage(event.target.value)} required minLength={1} maxLength={2000} rows={7} className="mt-1 block w-full rounded border p-2" />
      </label>
      <label className="block">返信先（任意・254文字まで）
        <input value={reply} onChange={event => setReply(event.target.value)} maxLength={254} className="mt-1 block w-full rounded border p-2" />
      </label>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <button type="submit" disabled={sending} className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50">{sending ? '送信中…' : '送信する'}</button>
    </form>}
  </div>
}
