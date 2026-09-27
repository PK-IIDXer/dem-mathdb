import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { symbolsApi } from '../../api/symbols'
import { formulasApi } from '../../api/formulas'
import { ApiError } from '../../api/client'
import type { FormulaDetail, FormulaParseResult, Symbol, Token } from '../../api/types'
import { Latex } from '../Latex'
import { NodeEditor } from './NodeEditor'
import {
  buildSymbolCompletionItems,
  renderLatex,
  renderPreview,
  serialize,
  tokensToTree,
  type EditorNode,
} from './model'
import { useCommand } from '../../commands/CommandProvider'
import { useDisplaySettings } from '../../DisplaySettingsContext'

interface FormulaEditorProps {
  onRegistered?: (formula: FormulaDetail) => void
  context?: Record<string, number>
  showSuggestions?: boolean
  showAdvanced?: boolean
  showRemarks?: boolean
}

function expectedType(error: ApiError | null): string | null {
  if (!error?.body || typeof error.body !== 'object' || !('details' in error.body)) return null
  const details = (error.body as { details?: unknown }).details
  if (!details || typeof details !== 'object' || !('expected_type' in details)) return null
  const value = (details as { expected_type?: unknown }).expected_type
  return typeof value === 'string' ? value : null
}

function completionAt(
  text: string,
  cursor: number,
  spellings: string[],
): { start: number; value: string } {
  const maximum = Math.max(0, ...spellings.map((spelling) => spelling.length))
  for (let start = Math.max(0, cursor - maximum); start < cursor; start += 1) {
    const value = text.slice(start, cursor)
    const lowered = value.toLocaleLowerCase()
    if (spellings.some((spelling) => spelling.toLocaleLowerCase().startsWith(lowered))) {
      return { start, value }
    }
  }
  return { start: cursor, value: '' }
}

export function FormulaEditor({
  onRegistered,
  context = {},
  showSuggestions = true,
  showAdvanced = true,
  showRemarks = true,
}: FormulaEditorProps) {
  const [text, setText] = useState('')
  const [cursor, setCursor] = useState(0)
  const [remarks, setRemarks] = useState('')
  const [parsed, setParsed] = useState<FormulaParseResult | null>(null)
  const [root, setRoot] = useState<EditorNode | null>(null)
  const [dss, setDss] = useState('')
  const [parseError, setParseError] = useState<ApiError | null>(null)
  const [treeConversionError, setTreeConversionError] = useState(false)
  const [treeSyncStatus, setTreeSyncStatus] = useState<'pending' | 'incomplete' | 'error' | null>(null)
  const [registerError, setRegisterError] = useState<string | null>(null)
  const [recent, setRecent] = useState<number[]>([])
  const [textRevision, setTextRevision] = useState(0)
  const requestSequence = useRef(0)
  const editorRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const symbolSearchRef = useRef<HTMLInputElement>(null)
  const symbolOriginRef = useRef<HTMLElement | null>(null)
  const [symbolPaletteOpen, setSymbolPaletteOpen] = useState(false)
  const [symbolQuery, setSymbolQuery] = useState('')
  const queryClient = useQueryClient()
  const { internals } = useDisplaySettings()

  const { data: symbols = [] } = useQuery({
    queryKey: ['symbols', 'with-usage'],
    queryFn: () => symbolsApi.listSymbols(undefined, true),
  })
  const { data: aliases = [] } = useQuery({
    queryKey: ['symbol-aliases'],
    queryFn: () => symbolsApi.listAliases(),
  })
  const { data: formulaTypes = [] } = useQuery({
    queryKey: ['formula-types'],
    queryFn: () => symbolsApi.listFormulaTypes(),
  })
  const symbolsById = useMemo(() => new Map(symbols.map((symbol) => [symbol.id, symbol])), [symbols])
  const displaySymbolsById = useMemo(() => {
    const reverse = new Map(Object.entries(context).map(([name, id]) => [id, name]))
    return new Map(symbols.map((symbol) => {
      const localName = reverse.get(symbol.id)
      return [symbol.id, localName ? { ...symbol, name: localName, latex_template: localName } : symbol]
    }))
  }, [context, symbols])
  const contextKey = JSON.stringify(context)

  useEffect(() => {
    const sequence = ++requestSequence.current
    if (!text.trim()) {
      setParsed(null)
      setRoot(null)
      setDss('')
      setParseError(null)
      setTreeConversionError(false)
      return
    }
    const timer = window.setTimeout(async () => {
      try {
        const result = await formulasApi.parse(text, JSON.parse(contextKey) as Record<string, number>)
        if (sequence !== requestSequence.current) return
        const treeResult = tokensToTree(result.tokens, symbolsById)
        if (!treeResult.ok) {
          // The server has already parsed and validated these tokens. A stale
          // symbol list may prevent the optional tree view from rendering,
          // but must not block registering the valid server result.
          setParsed(result)
          setRoot(null)
          setDss('')
          setParseError(null)
          setTreeConversionError(true)
          setTreeSyncStatus(null)
          return
        }
        setParsed(result)
        setRoot(treeResult.tree)
        setParseError(null)
        setTreeConversionError(false)
        setTreeSyncStatus(null)
        const printed = await formulasApi.print(result.tokens)
        if (sequence === requestSequence.current) setDss(printed.text)
      } catch (error) {
        if (sequence !== requestSequence.current) return
        setParsed(null)
        setRoot(null)
        setDss('')
        setParseError(error instanceof ApiError ? error : null)
        setTreeConversionError(false)
        setTreeSyncStatus(null)
      }
    }, 150)
    return () => window.clearTimeout(timer)
  }, [text, textRevision, contextKey, symbolsById])

  const treeLatex = useMemo(() => renderLatex(root, displaySymbolsById), [root, displaySymbolsById])
  const polish = useMemo(() => renderPreview(root, displaySymbolsById), [root, displaySymbolsById])
  const expected = expectedType(parseError)
  const aliasBySymbol = useMemo(() => {
    const result = new Map<number, string[]>()
    for (const alias of aliases) result.set(alias.symbol_id, [...(result.get(alias.symbol_id) ?? []), alias.alias])
    return result
  }, [aliases])
  const completionItems = useMemo(
    () => buildSymbolCompletionItems(symbols, aliasBySymbol, context),
    [aliasBySymbol, context, symbols],
  )
  const currentWord = completionAt(text, cursor, completionItems.map(({ matchSpelling }) => matchSpelling))
  const suggestions = useMemo(() => {
    if (!currentWord.value) return []
    const lowered = currentWord.value.toLocaleLowerCase()
    const expectedTypeId = formulaTypes.find((item) => item.name === expected)?.id
    return completionItems
      .filter(({ symbol, matchSpelling }) =>
        matchSpelling.toLocaleLowerCase().startsWith(lowered)
        && (expectedTypeId == null || symbol.symbol_type.output_formula_type_id === expectedTypeId),
      )
      .sort((left, right) => {
        const score = (item: { symbol: Symbol; isLocal: boolean }) => {
          const recentIndex = recent.indexOf(item.symbol.id)
          return (item.isLocal ? 200000 : 0)
            + (recentIndex < 0 ? 0 : 100000 - recentIndex)
            + (item.symbol.usage_count ?? 0)
        }
        return score(right) - score(left)
          || left.insertionSpelling.localeCompare(right.insertionSpelling)
      })
      .slice(0, 8)
  }, [completionItems, currentWord.value, expected, formulaTypes, recent])

  const registerMutation = useMutation({
    mutationFn: (tokens: Token[]) => formulasApi.register(tokens, remarks || undefined),
    onSuccess: (formula) => {
      queryClient.invalidateQueries({ queryKey: ['formulas'] })
      setParsed((value) => value ? { ...value, formula_id: formula.id } : value)
      onRegistered?.(formula)
      setRegisterError(null)
    },
    onError: (error) => setRegisterError(
      error instanceof ApiError ? error.message : '式を登録できませんでした',
    ),
  })

  async function chooseFormula() {
    if (!parsed) return
    if (parsed.formula_id != null) {
      onRegistered?.(await formulasApi.get(parsed.formula_id))
    } else {
      registerMutation.mutate(parsed.tokens)
    }
  }

  function changeText(next: string, nextCursor: number) {
    requestSequence.current += 1
    setText(next)
    setCursor(nextCursor)
    setTextRevision((value) => value + 1)
    setParsed(null)
    setRoot(null)
    setDss('')
    setParseError(null)
    setTreeConversionError(false)
    setTreeSyncStatus(null)
  }

  function openSymbolPalette() {
    symbolOriginRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setSymbolPaletteOpen(true)
    setSymbolQuery('')
  }

  function closeSymbolPalette() {
    setSymbolPaletteOpen(false)
    const origin = symbolOriginRef.current
    // The origin is gone when the palette was opened from the command palette,
    // whose input unmounts on close. Fall back to the editor's own input.
    const restored = origin && editorRef.current?.contains(origin) ? origin : textRef.current
    restored?.focus()
  }

  const runChooseFormula = useCommand('formula.commit', chooseFormula, {
    enabled: parsed != null && treeSyncStatus === null && !registerMutation.isPending,
    scope: editorRef,
  })
  const runSymbolPalette = useCommand('formula.symbols', openSymbolPalette, { scope: editorRef })
  useCommand('palette.close', closeSymbolPalette, { enabled: symbolPaletteOpen, scope: editorRef })

  useEffect(() => {
    if (symbolPaletteOpen) symbolSearchRef.current?.focus()
  }, [symbolPaletteOpen])

  async function changeTree(next: EditorNode | null) {
    const sequence = ++requestSequence.current
    setRoot(next)
    setParsed(null)
    setDss('')
    setParseError(null)
    setTreeConversionError(false)
    const serialized = serialize(next)
    if (!serialized) {
      setTreeSyncStatus('incomplete')
      return
    }
    setTreeSyncStatus('pending')
    try {
      const printed = await formulasApi.print(serialized.tokens)
      if (sequence !== requestSequence.current) return
      setText(printed.text)
      setCursor(printed.text.length)
      setTextRevision((value) => value + 1)
    } catch {
      if (sequence === requestSequence.current) setTreeSyncStatus('error')
    }
  }

  function applySuggestion(symbol: Symbol, spelling: string) {
    const suffix = symbol.arity > 0 && !symbol.symbol_type.is_quantifier && symbol.notation_kind === 'prefix'
      ? '('
      : symbol.symbol_type.is_quantifier ? ' ' : ''
    const next = `${text.slice(0, currentWord.start)}${spelling}${suffix}${text.slice(cursor)}`
    changeText(next, currentWord.start + spelling.length + suffix.length)
    setRecent([symbol.id, ...recent.filter((id) => id !== symbol.id)].slice(0, 20))
  }

  function insertSymbol(symbol: Symbol) {
    const spelling = Object.entries(context).find(([, id]) => id === symbol.id)?.[0] ?? symbol.name
    const next = `${text.slice(0, cursor)}${spelling}${text.slice(cursor)}`
    changeText(next, cursor + spelling.length)
    closeSymbolPalette()
  }

  const errorPosition = parseError?.position
  return (
    <div ref={editorRef} className="space-y-3 rounded-lg border border-slate-200 p-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">数式を入力</label>
        <textarea
          ref={textRef}
          value={text}
          rows={3}
          onChange={(event) => {
            changeText(event.target.value, event.target.selectionStart)
          }}
          onClick={(event) => setCursor(event.currentTarget.selectionStart)}
          onKeyUp={(event) => setCursor(event.currentTarget.selectionStart)}
          className={`w-full rounded border px-3 py-2 font-mono text-sm outline-none ${parseError ? 'border-red-300 focus:border-red-500' : 'border-slate-300 focus:border-indigo-500'}`}
          placeholder="例: forall x. P(x) -> Q(x)"
        />
        <button
          type="button"
          onClick={() => runSymbolPalette()}
          className="mt-1 rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
        >
          記号を挿入 <kbd aria-hidden="true">Ctrl/⌘ /</kbd>
        </button>
        {symbolPaletteOpen && (
          <div role="dialog" aria-modal="true" aria-label="記号を挿入" className="mt-2 rounded-lg border border-indigo-200 bg-white p-3 shadow-lg">
            <div className="flex items-center gap-2">
              <input
                ref={symbolSearchRef}
                value={symbolQuery}
                onChange={(event) => setSymbolQuery(event.target.value)}
                aria-label="記号を検索"
                className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
              />
              <button type="button" onClick={closeSymbolPalette} className="rounded px-2 py-1 text-xs text-slate-500">Esc</button>
            </div>
            <div className="mt-2 flex max-h-40 flex-wrap gap-1 overflow-y-auto">
              {symbols
                .filter((symbol) => !symbolQuery.trim() || [symbol.name, symbol.remarks ?? ''].some((value) => value.toLocaleLowerCase().includes(symbolQuery.trim().toLocaleLowerCase())))
                .slice(0, 100)
                .map((symbol) => (
                  <button key={symbol.id} type="button" onClick={() => insertSymbol(symbol)} className="rounded bg-slate-100 px-2 py-1 text-xs hover:bg-indigo-100">
                    {symbol.name}
                  </button>
                ))}
            </div>
          </div>
        )}
        {showSuggestions && suggestions.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {suggestions.map(({ symbol, insertionSpelling }) => (
              <button
                key={`${symbol.id}:${insertionSpelling}`}
                type="button"
                onClick={() => applySuggestion(symbol, insertionSpelling)}
                className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-indigo-100"
              >
                {insertionSpelling}{' '}
                <span className="text-slate-400">
                  {symbol.namespace_name} · {symbol.remarks ?? symbol.name}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {parseError && (
        <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <div>{parseError.message}</div>
          {errorPosition != null && (
            <code className="mt-1 block whitespace-pre-wrap text-xs">
              {text.slice(0, errorPosition)}<span className="underline decoration-2">{text[errorPosition] ?? ' '}</span>{text.slice(errorPosition + 1)}
            </code>
          )}
        </div>
      )}
      {treeConversionError && (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          この式は木で表示できません
        </p>
      )}
      {treeSyncStatus && (
        <p role="status" className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {treeSyncStatus === 'incomplete' && '未反映：木の未入力部分を埋めてください'}
          {treeSyncStatus === 'pending' && '未反映：テキストへ反映しています…'}
          {treeSyncStatus === 'error' && '未反映：テキストへ反映できませんでした'}
        </p>
      )}
      {registerError && <p className="text-sm text-red-700">{registerError}</p>}

      {root && (
        <div className="space-y-2">
          <div className="overflow-x-auto rounded border border-slate-100 bg-white px-3 py-3">
            <Latex display>{treeLatex}</Latex>
          </div>
          {parsed?.formula_id != null && (
            <p className="text-xs text-indigo-700">↳ 既存の式 #{parsed.formula_id} と同じです</p>
          )}
          {showAdvanced && parsed && <details open={internals === 'on'} className="text-xs text-slate-600">
            <summary className="cursor-pointer">▸ 内部表現</summary>
            <div className="mt-2 space-y-1 rounded bg-slate-50 p-2">
              <div>DSS: <code>{dss}</code></div>
              <div>polish: <code>{polish}</code></div>
              <div className="break-all">tokens: <code>{JSON.stringify(parsed.tokens)}</code></div>
            </div>
          </details>}
          {showAdvanced && <details className="text-xs text-slate-600">
            <summary className="cursor-pointer">木で見る</summary>
            <div className="mt-2 rounded border border-slate-100 bg-slate-50 p-3">
              <NodeEditor
                node={root}
                depth={0}
                symbols={symbols}
                symbolsById={displaySymbolsById}
                highlightedId={null}
                onChange={changeTree}
              />
            </div>
          </details>}
        </div>
      )}

      {showRemarks && <label className="block text-xs text-slate-500">
        メモ（任意）
        <input
          value={remarks}
          onChange={(event) => setRemarks(event.target.value)}
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
      </label>}
      <button
        type="button"
        disabled={!parsed || treeSyncStatus !== null || registerMutation.isPending}
        onClick={() => runChooseFormula()}
        className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
      >
        {parsed?.formula_id != null ? 'この式を選ぶ' : '確認して登録する'} <kbd aria-hidden="true" className="ml-1 text-xs">Ctrl/⌘ Enter</kbd>
      </button>
    </div>
  )
}
