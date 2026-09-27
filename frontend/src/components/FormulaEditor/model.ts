import type { Symbol, Token } from '../../api/types'

export interface SymbolNode {
  id: number
  kind: 'symbol'
  symbolId: number
  children: (EditorNode | null)[]
}

export interface BoundNode {
  id: number
  kind: 'bound'
  index: number
}

export type EditorNode = SymbolNode | BoundNode

export interface SymbolCompletionItem {
  symbol: Symbol
  matchSpelling: string
  insertionSpelling: string
  isLocal: boolean
}

export interface NamespaceSymbolGroup {
  namespace: string
  symbols: Symbol[]
}

export interface AmbiguousSymbolGroup {
  kind: 'name' | 'display'
  spelling: string
  symbols: Symbol[]
}

/** Mirrors SymbolTable.__post_init__: a short name is ambiguous exactly when
 * more than one symbol in the workspace owns it. */
export function ambiguousSymbolNames(symbols: Symbol[]): ReadonlySet<string> {
  const counts = new Map<string, number>()
  for (const symbol of symbols) counts.set(symbol.name, (counts.get(symbol.name) ?? 0) + 1)
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name))
}

/** Mirrors SymbolTable.spelling(), keeping inserted text parseable. */
export function symbolInputSpelling(symbol: Symbol, ambiguousNames: ReadonlySet<string>): string {
  return ambiguousNames.has(symbol.name) ? `${symbol.namespace_name}::${symbol.name}` : symbol.name
}

export function buildSymbolCompletionItems(
  symbols: Symbol[],
  aliasesBySymbol: ReadonlyMap<number, string[]>,
  context: Record<string, number>,
): SymbolCompletionItem[] {
  const localNames = new Map(Object.entries(context).map(([name, id]) => [id, name]))
  const ambiguousNames = ambiguousSymbolNames(symbols)
  return symbols.flatMap((symbol) => {
    const localName = localNames.get(symbol.id)
    const primary = localName ?? symbolInputSpelling(symbol, ambiguousNames)
    const candidates = [
      { matchSpelling: localName ?? symbol.name, insertionSpelling: primary },
      ...(aliasesBySymbol.get(symbol.id) ?? []).map((alias) => ({
        matchSpelling: alias,
        insertionSpelling: alias,
      })),
    ]
    const unique = new Map(candidates.map((item) => [item.insertionSpelling, item]))
    return [...unique.values()].map((item) => ({
      symbol,
      ...item,
      isLocal: localName !== undefined,
    }))
  })
}

export function groupSymbolsByNamespace(symbols: Symbol[]): NamespaceSymbolGroup[] {
  const grouped = new Map<string, Symbol[]>()
  for (const symbol of symbols) {
    grouped.set(symbol.namespace_name, [...(grouped.get(symbol.namespace_name) ?? []), symbol])
  }
  return [...grouped]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([namespace, items]) => ({
      namespace,
      symbols: [...items].sort((left, right) => left.name.localeCompare(right.name) || left.id - right.id),
    }))
}

function symbolDisplaySignature(symbol: Symbol): string {
  const template = (symbol.latex_template ?? symbol.name).trim()
  if (/#\d+/.test(template)) return `slots:${template.replace(/#\d+/g, '□')}`
  if (symbol.symbol_type.is_quantifier) return `binder:${template}`
  if (symbol.arity === 0) return `atom:${template}`
  if (symbol.notation_kind === 'infix') return `infix:${template}`
  return `apply:${template}:${symbol.arity}`
}

/** Lists both ambiguous parser spellings and cross-namespace display shapes. */
export function ambiguousSymbolGroups(symbols: Symbol[]): AmbiguousSymbolGroup[] {
  const groups: AmbiguousSymbolGroup[] = []
  const byName = new Map<string, Symbol[]>()
  const byDisplay = new Map<string, Symbol[]>()
  for (const symbol of symbols) {
    byName.set(symbol.name, [...(byName.get(symbol.name) ?? []), symbol])
    const signature = symbolDisplaySignature(symbol)
    byDisplay.set(signature, [...(byDisplay.get(signature) ?? []), symbol])
  }
  for (const [name, items] of byName) {
    if (items.length > 1) groups.push({ kind: 'name', spelling: name, symbols: items })
  }
  for (const items of byDisplay.values()) {
    if (items.length > 1 && new Set(items.map((item) => item.namespace_id)).size > 1) {
      groups.push({
        kind: 'display',
        spelling: items[0].latex_template ?? items[0].name,
        symbols: items,
      })
    }
  }
  return groups.sort((left, right) =>
    left.kind.localeCompare(right.kind) || left.spelling.localeCompare(right.spelling),
  )
}

let nextId = 1
export function freshId(): number {
  return nextId++
}

export function createSymbolNode(symbol: Symbol): SymbolNode {
  return {
    id: freshId(),
    kind: 'symbol',
    symbolId: symbol.id,
    children: Array.from({ length: symbol.arity }, () => null),
  }
}

export function createBoundNode(index = 0): BoundNode {
  return { id: freshId(), kind: 'bound', index }
}

/** Serializes the tree to polish-notation tokens, in lockstep with the node id
 * that produced each token (used to map a validation error position back to a
 * tree node for highlighting). Returns null if the tree has unfilled slots. */
export function serialize(node: EditorNode | null): { tokens: Token[]; nodeIds: number[] } | null {
  const tokens: Token[] = []
  const nodeIds: number[] = []

  function walk(current: EditorNode | null): boolean {
    if (current === null) return false
    if (current.kind === 'bound') {
      tokens.push({ de_bruijn_index: current.index })
      nodeIds.push(current.id)
      return true
    }
    tokens.push({ symbol_id: current.symbolId })
    nodeIds.push(current.id)
    for (const child of current.children) {
      if (!walk(child)) return false
    }
    return true
  }

  if (!walk(node)) return null
  return { tokens, nodeIds }
}

/** True for nodes that render as a single token with no internal structure
 * (bound-variable placeholders and arity-0 symbols), which never need
 * surrounding parentheses as an operand. */
function isAtomic(node: EditorNode | null): boolean {
  if (node === null) return true
  if (node.kind === 'bound') return true
  return node.children.length === 0
}

/** True when `node` is an infix application of `symbolId` sitting in the right
 * operand slot of the same symbol, i.e. the right-nesting that the encoding
 * uses for `∧`, `∨` and `→`.
 *
 * Such an operand may drop its parentheses: the *left* operand is still
 * parenthesized whenever it is not atomic, so `φ ∧ ψ ∧ ρ` can only have come
 * from `φ ∧ (ψ ∧ ρ)` — `(φ ∧ ψ) ∧ ρ` keeps its parentheses and stays distinct.
 * Chains of the same connective are common (a 5-conjunct antecedent nests four
 * deep) and the parentheses carried no information.
 * See docs/design/content/proof-step-reduction.md §15.6. */
function isRightAssociativeChain(
  node: EditorNode | null,
  symbolId: number,
  symbolsById: Map<number, Symbol>,
): boolean {
  if (node === null || node.kind !== 'symbol' || node.symbolId !== symbolId) return false
  const symbol = symbolsById.get(node.symbolId)
  return symbol?.notation_kind === 'infix' && node.children.length === 2
}

/** Renders an infix operand, adding parentheses whenever it is not atomic.
 * Prefix applications already parenthesize themselves in renderPreview's
 * base case, so they are used as-is to avoid doubling up. */
function renderInfixOperand(
  node: EditorNode | null,
  symbolsById: Map<number, Symbol>,
  binderNames: string[],
  bare = false,
  avoidNames?: Set<string>,
): string {
  const rendered = renderPreview(node, symbolsById, binderNames, avoidNames)
  if (isAtomic(node) || bare) return rendered
  const symbol = node && node.kind === 'symbol' ? symbolsById.get(node.symbolId) : undefined
  const isInfix = symbol?.notation_kind === 'infix' && node?.kind === 'symbol' && node.children.length === 2
  return isInfix ? `(${rendered})` : rendered
}

/**
 * Renders a tree as a human-readable string. Infix (arity-2) symbols are
 * shown as `left name right`. Each operand is parenthesized unless it is
 * atomic (a bound-variable placeholder or an arity-0 symbol such as a free
 * variable) — regardless of precedence — so that the display never collapses
 * two differently-grouped formulas into the same ambiguous text.
 *
 * The one exception is the right operand repeating the same symbol: `φ → (ψ →
 * χ)` renders as `φ → ψ → χ`, which stays distinct from `(φ → ψ) → χ` because
 * the left operand keeps its parentheses (`isRightAssociativeChain`).
 */
export function renderPreview(
  node: EditorNode | null,
  symbolsById: Map<number, Symbol>,
  binderNames: string[] = [],
  avoidNames?: Set<string>,
): string {
  const avoid = avoidNames ?? symbolNames(node, symbolsById)
  if (node === null) return '□' // placeholder square for an unfilled slot
  if (node.kind === 'bound') {
    return binderNames[binderNames.length - 1 - node.index] ?? `▢${node.index}`
  }
  const symbol = symbolsById.get(node.symbolId)
  const name = symbol?.name ?? `#${node.symbolId}`

  if (symbol?.symbol_type.is_quantifier) {
    const varName = freshBoundVarDisplayName(
      binderNames.length,
      new Set([...avoid, ...binderNames]),
    )
    const body = renderPreview(
      node.children[0] ?? null,
      symbolsById,
      [...binderNames, varName],
      avoid,
    )
    return `${name}${varName}. ${body}`
  }

  if (symbol?.notation_kind === 'infix' && node.children.length === 2) {
    const left = renderInfixOperand(node.children[0], symbolsById, binderNames, false, avoid)
    const right = renderInfixOperand(
      node.children[1],
      symbolsById,
      binderNames,
      isRightAssociativeChain(node.children[1], node.symbolId, symbolsById),
      avoid,
    )
    return `${left} ${name} ${right}`
  }

  if (node.children.length === 0) return name
  const childStrs = node.children.map((child) => renderPreview(child, symbolsById, binderNames, avoid))
  return `(${name} ${childStrs.join(' ')})`
}

const BOUND_VAR_BASE_NAMES = ['x', 'y', 'z']

function symbolNames(
  node: EditorNode | null,
  symbolsById: Map<number, Symbol>,
  names = new Set<string>(),
): Set<string> {
  if (node?.kind !== 'symbol') return names
  const symbol = symbolsById.get(node.symbolId)
  if (symbol) names.add(symbol.name)
  for (const child of node.children) symbolNames(child, symbolsById, names)
  return names
}

// Keep this in sync with demlang/printer.py. The naming contract is documented
// in docs/design/overview/conventions.md §4.
export function freshBoundVarDisplayName(depth: number, avoid: Set<string>): string {
  const preferred = boundVarDisplayName(depth)
  if (!avoid.has(preferred)) return preferred
  for (const suffix of ['′', '″']) {
    if (!avoid.has(`${preferred}${suffix}`)) return `${preferred}${suffix}`
  }
  let suffix = 1
  while (avoid.has(`${preferred}_${suffix}`)) suffix += 1
  return `${preferred}_${suffix}`
}

function displayNameToLatex(name: string): string {
  const match = /^(.*)_([0-9]+)$/.exec(name)
  return match ? `${match[1]}_{${match[2]}}` : name
}

/** Auto-generates a bound-variable display name from its binder depth (0 =
 * outermost): x, y, z, x_1, y_1, z_1, x_2, ... */
function boundVarLatexName(depth: number): string {
  const cycle = Math.floor(depth / BOUND_VAR_BASE_NAMES.length)
  const base = BOUND_VAR_BASE_NAMES[depth % BOUND_VAR_BASE_NAMES.length]
  return cycle === 0 ? base : `${base}_{${cycle}}`
}

function boundVarDisplayName(depth: number): string {
  const cycle = Math.floor(depth / BOUND_VAR_BASE_NAMES.length)
  const base = BOUND_VAR_BASE_NAMES[depth % BOUND_VAR_BASE_NAMES.length]
  return cycle === 0 ? base : `${base}_${cycle}`
}

const PLACEHOLDER = /#(\d)/
const PLACEHOLDER_GLOBAL = /#(\d)/g

export interface TemplateSlot {
  /** The argument as rendered. */
  latex: string
  /** True when it can sit beside a neighbouring symbol without parentheses. */
  selfContained: boolean
}

/**
 * Fills a `latex_template`'s slots, or returns null when it has none. For a
 * binder the slots are the bound variable and the body; for every other symbol
 * they are the arguments in order.
 *
 * A template without slots keeps the historical layout — one glyph in front
 * (`\forall x.\, body`, `f\left(a, b\right)`) — which covers prefix binders and
 * the ordinary function symbols ever needed. Symbols that *surround* their
 * arguments cannot be written that way: `\left\{\, #1, #2 \,\right\}` puts text
 * on both sides of its slots and `{#1}^{\mathrm{op}}` puts text after one.
 *
 * A slot with template text on both sides is filled raw — the text delimits it,
 * exactly as the `f(a, b)` form does with its parentheses and commas. **A slot
 * at either end of the template has nothing on that side**, so it is
 * parenthesized unless the argument brackets itself: `eval`'s `#1\left(#2\right)`
 * must render `(g ∘ f)(x)`, never `g ∘ f(x)`, which reads as `g ∘ (f(x))`.
 */
export function fillTemplate(template: string, slots: TemplateSlot[]): string | null {
  const trimmed = template.trim()
  if (!PLACEHOLDER.test(trimmed)) return null
  return trimmed.replace(PLACEHOLDER_GLOBAL, (match, index: string, offset: number) => {
    const slot = slots[Number(index) - 1]
    if (slot === undefined) return '\\square'
    const atEdge = offset === 0 || offset + match.length === trimmed.length
    return atEdge && !slot.selfContained ? `\\left(${slot.latex}\\right)` : slot.latex
  })
}

/**
 * Renders a `latex_template` on its own, for the places that display a symbol
 * outside any formula (the symbol list, the template editor's preview). A raw
 * `#1` is a KaTeX error, so the slots get stand-in arguments; every other
 * template is already displayable as written.
 */
export function renderTemplateSample(template: string, isQuantifier = false): string {
  const names = isQuantifier
    ? ['x', '\\varphi(x)']
    : Array.from({ length: 9 }, (_unused, i) => boundVarLatexName(i))
  const slots = names.map((latex) => ({ latex, selfContained: true }))
  return fillTemplate(template, slots) ?? template
}

/** True for a term that closes itself off, so it needs no parentheses beside a
 * neighbour. Two shapes qualify: the plain application `f\left(a, b\right)`,
 * and a template that *ends* in its own text — `{x | φ(x)}`, `C^{op}`,
 * `F_{a,b}(f)`. A leading slot is no obstacle, because `fillTemplate` already
 * parenthesizes an edge slot that needs it, so such a template begins with
 * either `\left(` or a single token.
 *
 * A template ending in a slot does not qualify — it runs into whatever sits
 * after it (`g ∘_C f`, `⋂_s A`) — and neither does an infix term or a
 * prefix-form binder (`\forall x.\, body`), which runs off to the right. */
function isSelfDelimiting(node: EditorNode | null, symbolsById: Map<number, Symbol>): boolean {
  if (node === null || node.kind !== 'symbol') return false
  const symbol = symbolsById.get(node.symbolId)
  const template = (symbol?.latex_template ?? '').trim()
  if (PLACEHOLDER.test(template)) return !/#\d$/.test(template)
  if (symbol?.symbol_type.is_quantifier || symbol?.notation_kind === 'infix') return false
  return node.children.length > 0
}

/**
 * Renders a tree as a LaTeX string, using each symbol's `latex_template`
 * (falling back to its plain name if unset). Quantifier symbols
 * (`symbol_type.is_quantifier`) introduce a fresh bound-variable name based on
 * nesting depth rather than rendering a child for the variable itself.
 * A template carrying `#n` slots lays out its own arguments (`fillTemplate`);
 * otherwise infix operands are parenthesized via the same atomicity rule as
 * `renderPreview`, and other applications use `token(arg, arg, ...)`.
 */
export function renderLatex(
  node: EditorNode | null,
  symbolsById: Map<number, Symbol>,
  binderNames: string[] = [],
  avoidNames?: Set<string>,
): string {
  const avoid = avoidNames ?? symbolNames(node, symbolsById)
  if (node === null) return '\\square'
  if (node.kind === 'bound') {
    const name = binderNames[binderNames.length - 1 - node.index]
    return name === undefined ? `\\square_{${node.index}}` : displayNameToLatex(name)
  }
  const symbol = symbolsById.get(node.symbolId)
  const token = symbol?.latex_template ?? symbol?.name ?? '?'

  const slot = (child: EditorNode | null): TemplateSlot => ({
    latex: renderLatex(child, symbolsById, binderNames, avoid),
    selfContained: isAtomic(child) || isSelfDelimiting(child, symbolsById),
  })

  if (symbol?.symbol_type.is_quantifier) {
    const displayVarName = freshBoundVarDisplayName(
      binderNames.length,
      new Set([...avoid, ...binderNames]),
    )
    const varName = displayNameToLatex(displayVarName)
    const body = renderLatex(
      node.children[0] ?? null,
      symbolsById,
      [...binderNames, displayVarName],
      avoid,
    )
    const filled = fillTemplate(token, [
      { latex: varName, selfContained: true },
      { latex: body, selfContained: isAtomic(node.children[0] ?? null) },
    ])
    return filled ?? `${token} ${varName}.\\, ${body}`
  }

  // Building slots recursively renders every child.  Do it only when the
  // template can consume them; otherwise the infix/application branches below
  // render the same children again and turn a deep tree into exponential work.
  if (node.children.length > 0 && PLACEHOLDER.test(token.trim())) {
    const filled = fillTemplate(token, node.children.map(slot))
    if (filled !== null) return filled
  }

  if (symbol?.notation_kind === 'infix' && node.children.length === 2) {
    const wrap = (child: EditorNode | null, chained = false) => {
      const rendered = renderLatex(child, symbolsById, binderNames, avoid)
      const bare = chained || isAtomic(child) || isSelfDelimiting(child, symbolsById)
      return bare ? rendered : `\\left(${rendered}\\right)`
    }
    const right = node.children[1]
    return `${wrap(node.children[0])} ${token} ${wrap(
      right,
      isRightAssociativeChain(right, node.symbolId, symbolsById),
    )}`
  }

  if (node.children.length === 0) return token
  const args = node.children.map((c) => renderLatex(c, symbolsById, binderNames, avoid))
  return `${token}\\left(${args.join(', ')}\\right)`
}

export type TreeBuildError =
  | { kind: 'unexpected-end'; position: number }
  | { kind: 'unknown-symbol'; position: number; symbolId: number }
  | { kind: 'invalid-token'; position: number }
  | { kind: 'trailing-tokens'; position: number }

export type TokensToTreeResult =
  | { ok: true; tree: EditorNode; consumed: number }
  | { ok: false; tree: null; consumed: number; error: TreeBuildError }

/** Rebuilds an EditorNode tree from a flat polish-notation token list.
 *
 * Success means that every token was consumed by one complete tree. Unknown
 * symbols, missing children, malformed tokens, and trailing tokens are
 * reported without returning the plausible-looking partial tree. Node ids are
 * synthetic and are not meant for validation highlighting. */
export function tokensToTree(tokens: Token[], symbolsById: Map<number, Symbol>): TokensToTreeResult {
  let cursor = 0
  let error: TreeBuildError | null = null

  function walk(): EditorNode | null {
    if (cursor >= tokens.length) {
      error = { kind: 'unexpected-end', position: cursor }
      return null
    }
    const position = cursor
    const token = tokens[cursor]
    cursor += 1
    const hasBoundIndex = token.de_bruijn_index != null
    const hasSymbolId = token.symbol_id != null
    if (hasBoundIndex === hasSymbolId) {
      error = { kind: 'invalid-token', position }
      return null
    }
    if (hasBoundIndex) {
      return { id: -cursor, kind: 'bound', index: token.de_bruijn_index as number }
    }
    const symbolId = token.symbol_id as number
    const symbol = symbolsById.get(symbolId)
    if (!symbol) {
      error = { kind: 'unknown-symbol', position, symbolId }
      return null
    }
    const children: (EditorNode | null)[] = []
    for (let i = 0; i < symbol.arity; i += 1) {
      const child = walk()
      if (child === null) return null
      children.push(child)
    }
    return { id: -cursor, kind: 'symbol', symbolId, children }
  }

  const tree = walk()
  if (tree === null) {
    return {
      ok: false,
      tree: null,
      consumed: cursor,
      error: error ?? { kind: 'invalid-token', position: cursor },
    }
  }
  if (cursor !== tokens.length) {
    return {
      ok: false,
      tree: null,
      consumed: cursor,
      error: { kind: 'trailing-tokens', position: cursor },
    }
  }
  return { ok: true, tree, consumed: cursor }
}
