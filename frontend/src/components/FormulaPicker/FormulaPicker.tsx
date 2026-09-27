import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { formulasApi } from '../../api/formulas'
import { symbolsApi } from '../../api/symbols'
import { FormulaEditor } from '../FormulaEditor'
import { renderLatex, tokensToTree } from '../FormulaEditor/model'
import { Latex } from '../Latex'

interface FormulaPickerProps {
  value: number | null
  onChange: (formulaId: number) => void
  context?: Record<string, number>
}

export function FormulaPicker({ value, onChange, context }: FormulaPickerProps) {
  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols'],
    queryFn: () => symbolsApi.listSymbols(),
  })
  const { data: selectedFormula } = useQuery({
    queryKey: ['formulas', value],
    queryFn: () => formulasApi.get(value as number),
    enabled: value != null,
  })
  const symbolsById = useMemo(() => new Map(symbols.map((symbol) => [symbol.id, symbol])), [symbols])
  const displaySymbolsById = useMemo(() => {
    const reverse = new Map(Object.entries(context ?? {}).map(([name, id]) => [id, name]))
    return new Map(symbols.map((symbol) => {
      const localName = reverse.get(symbol.id)
      return [symbol.id, localName ? { ...symbol, name: localName, latex_template: localName } : symbol]
    }))
  }, [context, symbols])
  const latex = useMemo(() => {
    if (!selectedFormula) return ''
    const tree = tokensToTree(selectedFormula.tokens, symbolsById).tree
    return tree ? renderLatex(tree, displaySymbolsById) : ''
  }, [displaySymbolsById, selectedFormula, symbolsById])

  return (
    <div className="space-y-2">
      <FormulaEditor context={context} onRegistered={(formula) => onChange(formula.id)} />
      {selectedFormula && (
        <div className="rounded border border-indigo-100 bg-indigo-50 p-2 text-xs text-indigo-800">
          選択中 #{selectedFormula.id}
          <Latex display>{latex}</Latex>
        </div>
      )}
    </div>
  )
}
