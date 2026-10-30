import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { subscribeWriteErrors, type ApiError } from '../api/client'
import { useBeta } from './BetaContext'

export function BetaWriteErrorNotice() {
  useLanguage()

  const beta = useBeta()
  const { pathname } = useLocation()
  const [failure, setFailure] = useState<{ path: string; error: ApiError } | null>(null)
  useEffect(() => {
    setFailure(null)
    return subscribeWriteErrors((error) => setFailure({ path: pathname, error }))
  }, [pathname])
  if (!beta || failure?.path !== pathname) return null
  return <div role="alert" className="fixed bottom-4 left-4 right-4 z-50 mx-auto max-h-[50vh] max-w-3xl overflow-y-auto rounded border border-red-200 bg-red-50 p-3 shadow-lg text-sm text-red-900">
    {failure.error.message}
    <button type="button" onClick={() => setFailure(null)} className="ml-3 underline">{t("CommandPalette_041")}</button>
  </div>
}
