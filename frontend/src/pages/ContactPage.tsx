import { useDisplayError } from "../i18n/useDisplayError"
import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useBeta } from '../components/BetaContext'
import { usePageTitle } from '../hooks/usePageTitle'

export function ContactPage() {
  useLanguage()

  usePageTitle(t("App_031"))
  const beta = useBeta()
  const [kind, setKind] = useState('other')
  const [target, setTarget] = useState('')
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useDisplayError()
  if (!beta) return <p>{t("ContactPage_544")}</p>

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!message.trim() || message.length > 2000 || target.length > 500 || reply.length > 254 ||
        (target !== '' && !/^(https?:\/\/|\/)/.test(target))) {
      setError(() => (t("errorGuidance_001")))
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
      setError(() => (failure instanceof ApiError ? failure.message : t("ContactPage_546")))
    } finally {
      setSending(false)
    }
  }

  return <div className="max-w-2xl space-y-4 text-sm text-slate-700">
    <h2 className="text-lg font-semibold">{t("App_031")}</h2>
    <p>{t("ContactPage_548")}</p>
    {accepted ? <p role="status">{t("ContactPage_549")}</p> : <form onSubmit={submit} className="space-y-4">
      <label className="block">{t("ContactPage_550")}<select value={kind} onChange={event => setKind(event.target.value)} className="ml-2 rounded border p-2">
          <option value="removal">{t("ContactPage_551")}</option><option value="bug">{t("ContactPage_552")}</option><option value="other">{t("ContactPage_553")}</option>
        </select>
      </label>
      {kind === 'removal' && <p>{t("ContactPage_554")}</p>}
      <label className="block">{t("ContactPage_555")}<input value={target} onChange={event => setTarget(event.target.value)} maxLength={500} className="mt-1 block w-full rounded border p-2" />
      </label>
      <label className="block">{t("ContactPage_556")}<textarea value={message} onChange={event => setMessage(event.target.value)} required minLength={1} maxLength={2000} rows={7} className="mt-1 block w-full rounded border p-2" />
      </label>
      <label className="block">{t("ContactPage_557")}<input value={reply} onChange={event => setReply(event.target.value)} maxLength={254} className="mt-1 block w-full rounded border p-2" />
      </label>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <button type="submit" disabled={sending} className="rounded bg-indigo-600 px-4 py-2 text-white disabled:opacity-50">{sending ? t("ContactPage_558") : t("ContactPage_559")}</button>
    </form>}
  </div>
}
