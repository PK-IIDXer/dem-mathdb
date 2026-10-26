import { useEffect } from 'react'

const SITE_NAME = 'Deus Ex Machina'

export function usePageTitle(name?: string) {
  useEffect(() => {
    document.title = name ? `${name} — ${SITE_NAME}` : SITE_NAME
    return () => { document.title = SITE_NAME }
  }, [name])
}
