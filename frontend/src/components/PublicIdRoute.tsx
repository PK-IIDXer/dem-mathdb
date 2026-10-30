import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { isPublicId } from '../publicId'

/** Do not mount a detail page (or any of its queries) for an internal ID. */
export function PublicIdRoute({ children }: { children: ReactNode }) {
  useLanguage()

  const { id, proofId } = useParams<{ id: string; proofId?: string }>()
  if (!isPublicId(id) || (proofId !== undefined && !isPublicId(proofId))) {
    return <p className="text-sm text-slate-400">{t("PublicIdRoute_362")}</p>
  }
  return children
}
