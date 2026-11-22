import type { Symbol } from '../../api/types'
import { t } from '../../i18n/translate'
import { renderLatex, tokensToTree } from '../FormulaEditor/model'
import { Latex } from '../Latex'

import type { ArgumentMismatch } from './argumentMismatch'

export function ArgumentMismatchMessage({ details, symbolsById }: { details: ArgumentMismatch; symbolsById: Map<number, Symbol> }) {
  const rows = [
    { label: t('stepExpectedPremise'), tokens: details.expected },
    { label: t('stepActualPremise'), tokens: details.actual },
  ]
  return (
    <div role="alert" className="space-y-1 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
      <p>{t('stepArgumentMismatch', details.premise)}</p>
      <dl>
        {rows.map(({ label, tokens }) => {
          const tree = Array.isArray(tokens) && tokensToTree(tokens, symbolsById).tree
          return tree && (
            <div key={label} className="flex flex-wrap items-baseline gap-2">
              <dt className="font-medium">{label}</dt>
              <dd><Latex>{renderLatex(tree, symbolsById)}</Latex></dd>
            </div>
          )
        })}
      </dl>
    </div>
  )
}
