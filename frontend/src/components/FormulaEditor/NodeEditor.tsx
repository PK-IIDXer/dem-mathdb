import type { Symbol } from '../../api/types'
import { createBoundNode, createSymbolNode, groupSymbolsByNamespace, type EditorNode } from './model'

interface NodeEditorProps {
  node: EditorNode | null
  depth: number
  symbols: Symbol[]
  symbolsById: Map<number, Symbol>
  highlightedId: number | null
  onChange: (node: EditorNode | null) => void
}

export function NodeEditor({
  node,
  depth,
  symbols,
  symbolsById,
  highlightedId,
  onChange,
}: NodeEditorProps) {
  if (node === null) {
    return <EmptySlot depth={depth} symbols={symbols} onChange={onChange} />
  }

  const isHighlighted = node.id === highlightedId

  if (node.kind === 'bound') {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-sm ${
          isHighlighted ? 'border-red-500 bg-red-50' : 'border-slate-300 bg-slate-50'
        }`}
      >
        <span className="font-mono">▢</span>
        <input
          type="number"
          min={0}
          value={node.index}
          onChange={(e) => onChange({ ...node, index: Number(e.target.value) })}
          className="w-12 rounded border border-slate-300 px-1"
        />
        <button
          type="button"
          onClick={() => onChange(null)}
          className="text-slate-400 hover:text-red-600"
          aria-label="clear"
        >
          ×
        </button>
      </span>
    )
  }

  const symbol = symbolsById.get(node.symbolId)
  const childDepth = symbol?.symbol_type.is_quantifier ? depth + 1 : depth

  return (
    <span
      className={`inline-flex flex-wrap items-center gap-1 rounded border px-2 py-1 text-sm ${
        isHighlighted ? 'border-red-500 bg-red-50' : 'border-indigo-200 bg-indigo-50'
      }`}
    >
      <span className="font-semibold text-indigo-900">{symbol?.name ?? `#${node.symbolId}`}</span>
      <button
        type="button"
        onClick={() => onChange(null)}
        className="text-slate-400 hover:text-red-600"
        aria-label="clear"
      >
        ×
      </button>
      {node.children.length > 0 && (
        <span className="ml-1 flex flex-wrap items-center gap-1">
          {node.children.map((child, index) => (
            <NodeEditor
              key={index}
              node={child}
              depth={childDepth}
              symbols={symbols}
              symbolsById={symbolsById}
              highlightedId={highlightedId}
              onChange={(next) => {
                const children = [...node.children]
                children[index] = next
                onChange({ ...node, children })
              }}
            />
          ))}
        </span>
      )}
    </span>
  )
}

function EmptySlot({
  depth,
  symbols,
  onChange,
}: {
  depth: number
  symbols: Symbol[]
  onChange: (node: EditorNode) => void
}) {
  const groups = groupSymbolsByNamespace(symbols)
  return (
    <span className="inline-flex items-center gap-1 rounded border border-dashed border-slate-400 bg-white px-2 py-1 text-sm">
      <select
        defaultValue=""
        onChange={(e) => {
          const symbol = symbols.find((s) => s.id === Number(e.target.value))
          if (symbol) onChange(createSymbolNode(symbol))
        }}
        className="rounded border border-slate-300 bg-white px-1 py-0.5 text-sm"
      >
        <option value="" disabled>
          記号を選択…
        </option>
        {groups.map((group) => (
          <optgroup key={group.namespace} label={group.namespace}>
            {group.symbols.map((symbol) => (
              <option key={symbol.id} value={symbol.id}>
                {symbol.name} ({symbol.symbol_type.name}, arity {symbol.arity})
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <span className="text-slate-300">|</span>
      <button
        type="button"
        onClick={() => onChange(createBoundNode(Math.max(depth - 1, 0)))}
        className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600 hover:bg-slate-200"
        title={`束縛変数を挿入 (現在のスコープ深度: ${depth})`}
      >
        ▢ 束縛変数 (深度 {depth})
      </button>
    </span>
  )
}
