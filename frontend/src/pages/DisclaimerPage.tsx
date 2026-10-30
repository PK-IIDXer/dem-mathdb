import { useLanguage } from '../i18n/useLanguage'
import { t } from '../i18n/translate'
import { usePageTitle } from '../hooks/usePageTitle'
import { useBeta } from '../components/BetaContext'
import { BetaLegalPage } from './BetaLegalPage'
import { StandardLegalPage } from './StandardLegalPage'

export function DisclaimerPage() {
  useLanguage()
  usePageTitle(t('App_034'))
  const beta = useBeta()
  return beta ? <BetaLegalPage kind="disclaimer" /> : <StandardLegalPage kind="disclaimer" />
}
