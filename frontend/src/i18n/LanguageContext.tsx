import { useEffect, type ReactNode } from 'react'
import { setLanguage } from './language'
import { t } from './translate'
import { useLanguage } from './useLanguage'

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language = useLanguage()
  useEffect(() => { document.documentElement.lang = language }, [language])
  return children
}

export function LanguageSwitch() {
  const language = useLanguage()
  return <div role="group" aria-label="Language" className="flex shrink-0 gap-1 text-sm">
    <button type="button" lang="ja" aria-label={t('languageJapanese')} aria-pressed={language === 'ja'} onClick={() => setLanguage('ja')} className="rounded px-2 py-1 aria-pressed:bg-indigo-100">{t('languageJapanese')}</button>
    <span aria-hidden="true">/</span>
    <button type="button" lang="en" aria-label="English" aria-pressed={language === 'en'} onClick={() => setLanguage('en')} className="rounded px-2 py-1 aria-pressed:bg-indigo-100">English</button>
  </div>
}
