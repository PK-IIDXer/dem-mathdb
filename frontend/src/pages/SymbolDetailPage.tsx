import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { symbolsApi } from '../api/symbols'
import { Latex } from '../components/Latex'
import { renderTemplateSample } from '../components/FormulaEditor/model'

export function SymbolDetailPage() {
  const { id } = useParams<{ id: string }>()
  const symbolRef = id ?? ''
  const { data: symbol } = useQuery({ queryKey: ['symbols', symbolRef], queryFn: () => symbolsApi.get(symbolRef) })

  if (!symbol) return <p className="text-sm text-slate-400">読み込み中…</p>

  return (
    <div className="space-y-4">
      <Link to="/symbols" className="text-xs text-indigo-600 hover:underline">
        ← 記号一覧に戻る
      </Link>
      <section className="space-y-3 rounded-lg border border-slate-200 p-4 text-sm">
        <div className="flex items-center justify-between">
          <span className="font-mono text-base text-slate-800">{symbol.name}</span>
          {symbol.latex_template && (
            <div className="rounded border border-slate-100 bg-white px-3 py-1 text-lg">
              <Latex>{renderTemplateSample(symbol.latex_template, symbol.symbol_type.is_quantifier)}</Latex>
            </div>
          )}
        </div>
        <div className="space-y-1 text-slate-600">
          <div>type: {symbol.symbol_type.name}</div>
          <div>arity: {symbol.arity}</div>
          <div>is_primitive: {symbol.is_primitive ? '✓' : '—'}</div>
          <div>
            表示形式: {symbol.notation_kind}
            {symbol.notation_kind === 'infix' && symbol.precedence != null ? ` (優先順位 ${symbol.precedence})` : ''}
          </div>
        </div>
        {symbol.remarks && <div className="text-slate-600">{symbol.remarks}</div>}
      </section>
    </div>
  )
}
