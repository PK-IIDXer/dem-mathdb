import { useLanguage } from "../i18n/useLanguage"
import { t } from "../i18n/translate"
import { useQuery } from '@tanstack/react-query'
import { theoremsApi } from '../api/theorems'
import { TheoremStatementPreview, theoremFormulaIds } from './TheoremStatementPreview'
import { usePrimeFormulas } from '../hooks/useFormulaLatex'
import type { Theorem } from '../api/types'

export function InferenceRulePicker({ onChoose, selectedId, testId }: {
  onChoose: (theorem: Theorem) => void
  selectedId?: number | ''
  testId?: string
}) {
  useLanguage()

  const { data: rules = [], isPending } = useQuery({
    queryKey: ['theorems', 'rules', 'picker'],
    queryFn: () => theoremsApi.listRules(),
    staleTime: 0,
  })
  const formulasWaiting = usePrimeFormulas(rules.flatMap(theoremFormulaIds))
  return (
    <div data-testid={testId} className="space-y-1 rounded border border-indigo-100 bg-indigo-50 p-2">
      {isPending && <p className="text-xs text-slate-500">{t("InferenceRulePicker_227")}</p>}
      {!isPending && rules.length === 0 && <p className="text-xs text-slate-500">{t("InferenceRulePicker_228")}</p>}
      {rules.map((theorem) => (
        <button
          key={theorem.id}
          type="button"
          onClick={() => onChoose(theorem)}
          className={`block w-full rounded px-2 py-1 text-left text-xs hover:bg-indigo-100 ${selectedId === theorem.id ? 'bg-indigo-200' : 'bg-white'}`}
        >
          <span className="font-semibold">{theorem.name}</span>
          <span className="ml-2 text-slate-500">{t("InferenceRulePicker_229")}{theorem.premise_formula_ids.length} {t("InferenceRulePicker_230")}</span>
          <TheoremStatementPreview theorem={theorem} formulasWaiting={formulasWaiting} />
        </button>
      ))}
    </div>
  )
}
