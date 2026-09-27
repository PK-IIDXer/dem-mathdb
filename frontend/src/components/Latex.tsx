import { useMemo } from 'react'
import katex from 'katex'

interface LatexProps {
  children: string
  display?: boolean
}

/** Renders a LaTeX string via KaTeX. Parse errors render as KaTeX's inline
 * error markup instead of throwing, since templates are free-form user input. */
export function Latex({ children, display = false }: LatexProps) {
  const html = useMemo(
    () => katex.renderToString(children, { throwOnError: false, displayMode: display }),
    [children, display],
  )
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}
