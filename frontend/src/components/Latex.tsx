import { useMemo } from 'react'
import { useBeta } from './BetaContext'
import { renderDisplayLatex } from './latexDisplay'

interface LatexProps {
  children: string
  display?: boolean
}

/** Renders a LaTeX string via KaTeX. Parse errors render as KaTeX's inline
 * error markup instead of throwing, since templates are free-form user input. */
export function Latex({ children, display = false }: LatexProps) {
  const beta = !!useBeta()
  // React compares dangerouslySetInnerHTML by object identity, so a fresh
  // object would re-assign innerHTML (and re-parse the KaTeX markup) on every
  // re-render even when the formula is unchanged.
  const markup = useMemo(
    () => {
      const html = renderDisplayLatex(children, display, beta)
      return html === null ? null : { __html: html }
    },
    [children, display, beta],
  )
  return markup ? <span className="inline-block max-w-full overflow-x-auto align-middle" dangerouslySetInnerHTML={markup} />
    : <span className="text-xs text-slate-500">表示できない式</span>
}
