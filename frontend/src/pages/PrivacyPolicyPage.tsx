import { useLanguage } from '../i18n/useLanguage'
import { t } from '../i18n/translate'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBeta } from '../components/BetaContext'
import { BetaLegalPage } from './BetaLegalPage'
import { StandardLegalPage } from './StandardLegalPage'

export function PrivacyPolicyPage() {
  useLanguage()
  usePageTitle(t('App_033'))
  const beta = useBeta()
  return beta ? <BetaLegalPage kind="privacy" /> : <StandardLegalPage kind="privacy" />
}
