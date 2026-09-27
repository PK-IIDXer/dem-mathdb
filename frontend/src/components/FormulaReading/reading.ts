import type { Symbol, Token } from '../../api/types'
import { freshBoundVarDisplayName, tokensToTree, type EditorNode } from '../FormulaEditor/model'

/**
 * Mechanical Japanese reading of a formula (N9.10 ②,
 * docs/design/ux/proposition-explanation.md §2 and §4).
 *
 * The reading is display-only. It is computed from the token tree the page
 * already holds, never sent anywhere, and never consulted by validation.
 *
 * Where a symbol's reading comes from, in order:
 * 1. `COMMON_READINGS`: the 9 symbols of the public logical core, keyed by public ID.
 * 2. The symbol's `remarks`, when it starts with `Name(p1,p2,...): meaning`
 *    and the parameters can be substituted safely (`parseRemarkTemplate`),
 *    or, for a binder, `Name x. φ: sentence` (`parseBinderTemplate`).
 * 3. Otherwise the symbol is shown by name, as the DSS printer writes it.
 *
 * Workspace-specific symbols are read from their remarks, never from this file.
 *
 * Propositions are read; terms are written as DSS text (the printer's layout
 * and bound-variable names), so every variable in a reading is the one in the
 * formula displayed next to it.
 */

type CommonReading =
  | { kind: 'bot' | 'not' | 'and' | 'or' | 'imp' | 'iff' }
  | { kind: 'relation'; read: (left: string, right: string) => string }
  | { kind: 'forall'; domain: string }
  | { kind: 'exists'; domain: string; unique: boolean }

/** The public logical core (`⊥ ¬ ∨ ∧ → ↔ ∀ ∃ =`), keyed by
 * the public ID so a renamed or same-named user symbol never picks up a
 * logical reading. */
export const COMMON_READINGS: ReadonlyMap<string, CommonReading> = new Map<string, CommonReading>([
  ['3200b32b-2960-5ad9-98b0-3c46eea42f9c', { kind: 'bot' }], // ⊥
  ['7ef55380-cb00-59f7-989f-1347cab26b12', { kind: 'not' }], // ¬
  ['e9ab484b-d683-5276-987a-af3df5a6e8e9', { kind: 'or' }], // ∨
  ['473e2256-e6c2-5c2a-b45b-7c39f69519e1', { kind: 'and' }], // ∧
  ['e72831d9-19bc-5094-abd7-359f275f87a1', { kind: 'imp' }], // →
  ['f4243ce5-6563-52e2-ac75-15de5e49cdec', { kind: 'iff' }], // ↔
  // ∀ / ∃ run over every well-formed term.
  ['893f7c1c-3e22-564f-a976-0a8e8e241f62', { kind: 'forall', domain: '項' }], // ∀
  ['b299df13-8ca1-5327-9b4c-f08b1231a678', { kind: 'exists', domain: '項', unique: false }], // ∃
  ['9c6f5697-7475-52bd-b600-b981e924af62', { kind: 'relation', read: (a, b) => `${a} と ${b} が等しい` }], // =
])

// ---------------------------------------------------------------------------
// Templates from symbol remarks

export type RemarkTemplateResult =
  | { ok: true; params: string[]; sentence: string; missing: string[] }
  | { ok: false; reason: RemarkRejection }

export type RemarkRejection =
  | 'no-remarks'
  | 'not-head-form'
  | 'arity-mismatch'
  | 'bad-parameter'
  | 'unsafe-substitution'
  | 'not-a-clause'
  | 'not-a-binder'

const REMARK_HEAD = /^([^\s():：]+)\(([^()]*)\)\s*[:：]\s*([\s\S]+)$/u
// A binder's remark: `Name variable. body: sentence`.
const BINDER_HEAD = /^([^\s():：]+)\s+([^\s.:：]+)\s*\.\s*([^\s.:：]+)\s*[:：]\s*([\s\S]+)$/u
// Identifier characters: ASCII letters and digits, Greek, primes. `_`, spaces,
// punctuation, arrows and Japanese are boundaries.
const IDENTIFIER_RUN = /[A-Za-z0-9\u0370-\u03FF\u2032\u2033]+/gu
const PARAMETER = /^[A-Za-z\u0370-\u03FF][A-Za-z0-9\u0370-\u03FF\u2032\u2033]*$/u
// Sub/superscript letters (`1ₐ`, `1ᶜ`) name a parameter in a form that
// cannot be rewritten to another name, so such a remark is never substituted.
const SCRIPT_LETTER = /[\u1D2C-\u1D6A\u1D9C-\u1DBF\u2090-\u209C\u2071\u207F]/u

/**
 * Reads a remark of the form `Name(p1,...,pn): meaning` as a template.
 *
 * Only the first sentence is used (up to `。` or `、すなわち`, without a
 * trailing full-width parenthetical such as `（通常の等号）`); the rest stays in the symbol-meaning list.
 * Substitution is by whole identifier runs, all at
 * once, so `a` never matches inside another word and a parameter never matches
 * inside another parameter. The template is refused — and the symbol falls
 * back to its name — whenever that cannot be done safely:
 * - the parameter count differs from the arity;
 * - the sentence contains a short identifier that is not a parameter (it could
 *   collide with a substituted variable name) or a sub/superscript letter;
 * - for a predicate, the sentence is not a clause.
 *
 * A parameter the sentence never mentions (`Monomorphism(C,a,b,f): f が左簡約可能`)
 * is not dropped: the reading appends it as `（C = x、a = y、b = z）`.
 */
export function parseRemarkTemplate(symbol: Symbol, isPredicate: boolean): RemarkTemplateResult {
  const remarks = symbol.remarks?.trim()
  if (!remarks) return { ok: false, reason: 'no-remarks' }
  const match = REMARK_HEAD.exec(remarks)
  if (!match) return { ok: false, reason: 'not-head-form' }
  const params = match[2].split(',').map((param) => param.trim())
  if (params.length !== symbol.arity) return { ok: false, reason: 'arity-mismatch' }
  if (params.some((param) => !PARAMETER.test(param)) || new Set(params).size !== params.length) {
    return { ok: false, reason: 'bad-parameter' }
  }
  let sentence = firstSentence(match[3])
  if (SCRIPT_LETTER.test(sentence)) return { ok: false, reason: 'unsafe-substitution' }
  const seen = new Set<string>()
  for (const [run] of sentence.matchAll(IDENTIFIER_RUN)) {
    if (params.includes(run)) {
      seen.add(run)
    } else if (!/^[0-9]+$/.test(run) && run.length < 3) {
      return { ok: false, reason: 'unsafe-substitution' }
    }
  }
  if (isPredicate) {
    const clause = toClause(sentence)
    if (clause === null) return { ok: false, reason: 'not-a-clause' }
    sentence = clause
  }
  return { ok: true, params, sentence, missing: params.filter((param) => !seen.has(param)) }
}

/** The first sentence of a remark: up to `。` or `、すなわち`, without a
 * trailing full-width parenthetical. */
function firstSentence(text: string): string {
  let sentence = text.split('。')[0]
  const namely = sentence.indexOf('、すなわち')
  if (namely >= 0) sentence = sentence.slice(0, namely)
  return sentence.trim().replace(/\s*（[^（）]*）$/u, '')
}

export type BinderTemplateResult =
  | { ok: true; template: BinderTemplate }
  | { ok: false; reason: RemarkRejection }

/** A proposition binder's reading, from a remark `Name x. φ: sentence`. */
export interface BinderTemplate {
  variable: string
  body: string
  sentence: string
  /** The sentence ends with the body (`すべての x について、φ`): a run of the
   * same binder then reads as one (`すべての x、y について、…`) and the body is
   * not quoted. Otherwise the body is quoted in place and never merged. */
  prefix: boolean
}

/**
 * Reads the remark of a binder that makes a proposition (lean-import-design
 * §5.3). The variable and the body must each appear exactly once in the first
 * sentence, and any other short identifier makes the template unsafe, as in
 * `parseRemarkTemplate`; otherwise the binder falls back to its name.
 */
export function parseBinderTemplate(symbol: Symbol): BinderTemplateResult {
  const remarks = symbol.remarks?.trim()
  if (!remarks) return { ok: false, reason: 'no-remarks' }
  const match = BINDER_HEAD.exec(remarks)
  if (!match) return { ok: false, reason: 'not-head-form' }
  const [variable, body] = [match[2], match[3]]
  if (!PARAMETER.test(variable) || !PARAMETER.test(body) || variable === body) {
    return { ok: false, reason: 'bad-parameter' }
  }
  const sentence = firstSentence(match[4])
  if (SCRIPT_LETTER.test(sentence)) return { ok: false, reason: 'unsafe-substitution' }
  const runs = [...sentence.matchAll(IDENTIFIER_RUN)]
  for (const [run] of runs) {
    if (run !== variable && run !== body && !/^[0-9]+$/.test(run) && run.length < 3) {
      return { ok: false, reason: 'unsafe-substitution' }
    }
  }
  const count = (name: string) => runs.filter(([run]) => run === name).length
  if (count(variable) !== 1 || count(body) !== 1) return { ok: false, reason: 'not-a-binder' }
  const last = runs[runs.length - 1]
  const prefix = last[0] === body && (last.index ?? 0) + body.length === sentence.length
  return { ok: true, template: { variable, body, sentence, prefix } }
}

/** Fills a binder template in one pass: the variable with the bound names, the
 * body with its text. A corner bracket needs no space beside a Japanese word,
 * so `φ を満たす x` reads `「…」を満たす x`, as `connect` does for かつ / または. */
function fillBinder(template: BinderTemplate, vars: string[], body: string): string {
  let text = ''
  let read = 0
  for (const match of template.sentence.matchAll(IDENTIFIER_RUN)) {
    const run = match[0]
    const at = match.index ?? 0
    const replacement =
      run === template.variable ? vars.join('、') : run === template.body ? body : run
    let before = template.sentence.slice(read, at)
    if (replacement.startsWith('「') && before.endsWith(' ')) before = before.slice(0, -1)
    text += before + replacement
    read = at + run.length
    if (replacement.endsWith('」') && template.sentence[read] === ' ') read += 1
  }
  return text + template.sentence.slice(read)
}

const JAPANESE_END = /[\u3040-\u30FF\u3400-\u9FFF]$/u

function toClause(sentence: string): string | null {
  if (sentence.endsWith('こと')) return sentence.slice(0, -2)
  if (sentence.includes('が')) return JAPANESE_END.test(sentence) ? `${sentence}である` : `${sentence} である`
  return null
}

export interface RemarkTemplate {
  params: string[]
  sentence: string
  /** Parameters the sentence does not mention, appended as `（C = x）`. */
  missing: string[]
}

/** Replaces every parameter occurrence in one pass (so `(x, y) ↦ (y, x)` swaps). */
export function substituteTemplate(template: RemarkTemplate, args: string[]): string {
  const text = template.sentence.replace(IDENTIFIER_RUN, (run) => {
    const index = template.params.indexOf(run)
    return index < 0 ? run : args[index]
  })
  if (template.missing.length === 0) return text
  const rest = template.missing.map((param) => `${param} = ${args[template.params.indexOf(param)]}`)
  return `${text}（${rest.join('、')}）`
}

// ---------------------------------------------------------------------------
// Classification

export type SymbolReadingSource = 'common' | 'remark' | 'variable' | 'name'

export interface SymbolReadingInfo {
  source: SymbolReadingSource
  template?: RemarkTemplate
  binder?: BinderTemplate
  rejection?: RemarkRejection
}

const FREE_VARIABLE_TYPES = new Set(['項型自由変数記号', '命題型自由変数記号'])

/** `propositionTypeId` is the formula type id of propositions. */
export function classifySymbol(symbol: Symbol, propositionTypeId: number): SymbolReadingInfo {
  if (COMMON_READINGS.has(symbol.public_id)) return { source: 'common' }
  if (FREE_VARIABLE_TYPES.has(symbol.symbol_type.name)) return { source: 'variable' }
  if (symbol.symbol_type.is_quantifier) {
    // Term-valued binders are written as terms, as the printer does.
    if (symbol.symbol_type.output_formula_type_id !== propositionTypeId) {
      return { source: 'name', rejection: 'not-head-form' }
    }
    const binder = parseBinderTemplate(symbol)
    return binder.ok ? { source: 'remark', binder: binder.template } : { source: 'name', rejection: binder.reason }
  }
  const parsed = parseRemarkTemplate(symbol, symbol.symbol_type.output_formula_type_id === propositionTypeId)
  return parsed.ok
    ? { source: 'remark', template: { params: parsed.params, sentence: parsed.sentence, missing: parsed.missing } }
    : { source: 'name', rejection: parsed.reason }
}

// ---------------------------------------------------------------------------
// Reading tree

type Read =
  | { t: 'atom'; text: string; bare: boolean }
  | { t: 'bot' }
  | { t: 'not'; body: Read }
  | { t: 'and' | 'or'; items: Read[] }
  | { t: 'imp'; antecedents: Read[]; consequent: Read }
  | { t: 'iff'; left: Read; right: Read }
  | { t: 'forall'; domain: string; vars: string[]; body: Read }
  | { t: 'exists'; domain: string; unique: boolean; vars: string[]; body: Read }
  | { t: 'binder'; symbolId: number; template: BinderTemplate; vars: string[]; body: Read }

/** A reading laid out for display: one sentence, or a lead sentence with
 * numbered items that are themselves readings. */
export interface ReadingBlock {
  text: string
  items?: ReadingBlock[]
}

export interface FormulaReading {
  /** The whole reading as one sentence. */
  sentence: string
  /** The same reading split into items when it is long. */
  block: ReadingBlock
  /** Non-variable symbols read by their name because no template applied. */
  nameFallbackSymbolIds: number[]
  /** Every symbol in the formula, in order of first appearance. */
  symbolIds: number[]
}

export interface ReadingOptions {
  /** A reading longer than this many characters is split into items. */
  splitLength?: number
  /** How many levels of items may nest. */
  maxDepth?: number
}

/** Chosen on the explanation popover: its reading area is about 448px wide,
 * 32 full-width characters of text-sm a line. Past two lines a one-sentence
 * reading stops being scannable. A reading that needs 「」 inside 「」 is split
 * at any length, because nested quotes cannot be matched by eye. See
 * docs/design/ux/proposition-explanation.md §4. */
export const READING_SPLIT_LENGTH = 64
export const READING_SPLIT_QUOTE_DEPTH = 2
export const READING_MAX_DEPTH = 3

interface Context {
  symbolsById: Map<number, Symbol>
  propositionTypeId: number
  info: Map<number, SymbolReadingInfo>
  used: Set<string>
  fallback: Set<number>
  seen: number[]
}

export function readTokens(
  tokens: Token[],
  symbolsById: Map<number, Symbol>,
  options: ReadingOptions = {},
): FormulaReading | null {
  const built = tokensToTree(tokens, symbolsById)
  return built.ok ? readFormula(built.tree, symbolsById, options) : null
}

/** Reads a proposition. Returns null for a term or an unfilled tree. */
export function readFormula(
  root: EditorNode,
  symbolsById: Map<number, Symbol>,
  options: ReadingOptions = {},
): FormulaReading | null {
  if (root.kind !== 'symbol' || !isComplete(root)) return null
  const rootSymbol = symbolsById.get(root.symbolId)
  if (!rootSymbol) return null
  const ctx: Context = {
    symbolsById,
    // A step conclusion, premise or theorem statement is a proposition, so
    // its root's output type is the proposition type.
    propositionTypeId: rootSymbol.symbol_type.output_formula_type_id,
    info: new Map(),
    used: symbolNames(root, symbolsById),
    fallback: new Set(),
    seen: [],
  }
  collectSymbols(root, ctx)
  const tree = readProposition(root, ctx, [])
  const splitLength = options.splitLength ?? READING_SPLIT_LENGTH
  const maxDepth = options.maxDepth ?? READING_MAX_DEPTH
  return {
    sentence: linear(tree),
    block: layout(tree, splitLength, maxDepth),
    nameFallbackSymbolIds: [...ctx.fallback],
    symbolIds: ctx.seen,
  }
}

function isComplete(node: EditorNode | null): boolean {
  if (node === null) return false
  if (node.kind === 'bound') return true
  return node.children.every(isComplete)
}

function symbolNames(node: EditorNode, symbolsById: Map<number, Symbol>, names = new Set<string>()): Set<string> {
  if (node.kind !== 'symbol') return names
  const symbol = symbolsById.get(node.symbolId)
  if (symbol) names.add(symbol.name)
  for (const child of node.children) if (child) symbolNames(child, symbolsById, names)
  return names
}

function collectSymbols(node: EditorNode, ctx: Context) {
  if (node.kind !== 'symbol') return
  if (!ctx.seen.includes(node.symbolId)) ctx.seen.push(node.symbolId)
  for (const child of node.children) if (child) collectSymbols(child, ctx)
}

function infoOf(symbol: Symbol, ctx: Context): SymbolReadingInfo {
  let info = ctx.info.get(symbol.id)
  if (!info) {
    info = classifySymbol(symbol, ctx.propositionTypeId)
    ctx.info.set(symbol.id, info)
  }
  return info
}

/** The bound-variable name for the next binder, exactly as
 * demlang/printer.py `_bound_name` and FormulaEditor `renderPreview` choose it. */
function bind(scope: string[], ctx: Context): string {
  return freshBoundVarDisplayName(scope.length, new Set([...ctx.used, ...scope]))
}

function readProposition(node: EditorNode, ctx: Context, scope: string[]): Read {
  if (node.kind === 'bound') return { t: 'atom', text: printNode(node, ctx, scope), bare: true }
  const symbol = ctx.symbolsById.get(node.symbolId) as Symbol
  const common = COMMON_READINGS.get(symbol.public_id)
  const child = (index: number) => node.children[index] as EditorNode
  if (common) {
    switch (common.kind) {
      case 'bot': return { t: 'bot' }
      case 'not': return { t: 'not', body: readProposition(child(0), ctx, scope) }
      case 'and':
      case 'or': {
        const items = [readProposition(child(0), ctx, scope)]
        const right = readProposition(child(1), ctx, scope)
        // Only the right operand continues a chain: the encoding nests
        // `φ ∧ ψ ∧ ρ` to the right, as the printer does.
        if (right.t === common.kind && sameSymbol(child(1), node)) items.push(...right.items)
        else items.push(right)
        return { t: common.kind, items }
      }
      case 'imp': {
        const antecedent = readProposition(child(0), ctx, scope)
        const consequent = readProposition(child(1), ctx, scope)
        const antecedents = antecedent.t === 'and' ? [...antecedent.items] : [antecedent]
        if (consequent.t === 'imp' && sameSymbol(child(1), node)) {
          return { t: 'imp', antecedents: [...antecedents, ...consequent.antecedents], consequent: consequent.consequent }
        }
        return { t: 'imp', antecedents, consequent }
      }
      case 'iff':
        return { t: 'iff', left: readProposition(child(0), ctx, scope), right: readProposition(child(1), ctx, scope) }
      case 'forall':
      case 'exists': {
        const name = bind(scope, ctx)
        const body = readProposition(child(0), ctx, [...scope, name])
        const sameBinder = sameSymbol(child(0), node)
        if (common.kind === 'forall') {
          if (body.t === 'forall' && sameBinder) return { ...body, vars: [name, ...body.vars] }
          return { t: 'forall', domain: common.domain, vars: [name], body }
        }
        if (body.t === 'exists' && sameBinder && !common.unique) return { ...body, vars: [name, ...body.vars] }
        return { t: 'exists', domain: common.domain, unique: common.unique, vars: [name], body }
      }
      case 'relation':
        return {
          t: 'atom',
          text: common.read(printArgument(child(0), ctx, scope), printArgument(child(1), ctx, scope)),
          bare: false,
        }
    }
  }
  const info = infoOf(symbol, ctx)
  if (info.source === 'remark' && info.binder) {
    const name = bind(scope, ctx)
    const body = readProposition(child(0), ctx, [...scope, name])
    if (info.binder.prefix && body.t === 'binder' && body.symbolId === symbol.id) {
      return { ...body, vars: [name, ...body.vars] }
    }
    return { t: 'binder', symbolId: symbol.id, template: info.binder, vars: [name], body }
  }
  if (info.source === 'remark' && info.template) {
    const args = node.children.map((argument) => printArgument(argument as EditorNode, ctx, scope))
    return { t: 'atom', text: substituteTemplate(info.template, args), bare: false }
  }
  if (info.source !== 'variable') ctx.fallback.add(symbol.id)
  return { t: 'atom', text: printNode(node, ctx, scope), bare: true }
}

function sameSymbol(child: EditorNode, parent: EditorNode): boolean {
  return child.kind === 'symbol' && parent.kind === 'symbol' && child.symbolId === parent.symbolId
}

// ---------------------------------------------------------------------------
// DSS text for terms (a port of demlang/printer.py `_render`)

function isAtomicNode(node: EditorNode, ctx: Context): boolean {
  if (node.kind === 'bound') return true
  return (ctx.symbolsById.get(node.symbolId)?.arity ?? 0) === 0
}

function printNode(node: EditorNode, ctx: Context, scope: string[]): string {
  if (node.kind === 'bound') return scope[scope.length - 1 - node.index] ?? `▢${node.index}`
  const symbol = ctx.symbolsById.get(node.symbolId) as Symbol
  const child = (index: number) => node.children[index] as EditorNode
  if (symbol.symbol_type.is_quantifier) {
    const name = bind(scope, ctx)
    return `${symbol.name} ${name}. ${printNode(child(0), ctx, [...scope, name])}`
  }
  if (symbol.arity === 0) return symbol.name
  if (symbol.notation_kind === 'infix' && node.children.length === 2) {
    let left = printNode(child(0), ctx, scope)
    let right = printNode(child(1), ctx, scope)
    if (!isAtomicNode(child(0), ctx)) left = `(${left})`
    if (!isAtomicNode(child(1), ctx) && !sameSymbol(child(1), node)) right = `(${right})`
    return `${left} ${symbol.name} ${right}`
  }
  return `${symbol.name}(${node.children.map((c) => printNode(c as EditorNode, ctx, scope)).join(', ')})`
}

/** The whole formula as DSS text. It must equal demlang/printer.py
 * `print_dss` (bound names included); the reading writes terms with it. */
export function printFormula(tokens: Token[], symbolsById: Map<number, Symbol>): string | null {
  const built = tokensToTree(tokens, symbolsById)
  if (!built.ok) return null
  const ctx: Context = {
    symbolsById,
    propositionTypeId: -1,
    info: new Map(),
    used: symbolNames(built.tree, symbolsById),
    fallback: new Set(),
    seen: [],
  }
  return printNode(built.tree, ctx, [])
}

/** A term placed inside a sentence: parenthesized unless it is a name or a
 * prefix application, which already delimit themselves. */
function printArgument(node: EditorNode, ctx: Context, scope: string[]): string {
  const text = printNode(node, ctx, scope)
  if (node.kind === 'bound' || isAtomicNode(node, ctx)) return text
  const symbol = ctx.symbolsById.get(node.symbolId) as Symbol
  const delimited = !symbol.symbol_type.is_quantifier && symbol.notation_kind !== 'infix'
  return delimited ? text : `(${text})`
}

// ---------------------------------------------------------------------------
// Linear sentences

// Japanese text and the corner brackets need no space beside a Japanese word;
// math text (`φ`, `Set(x)`) does.
const TIGHT_END = /[\u3001\u3040-\u30FF\u3400-\u9FFF\u300C\u300D]$/u
const BRACKET_END = /\u300D$/u
const BRACKET_START = /^\u300C/u

/** Appends a Japanese word to a clause, with a space after math text. */
function join(left: string, word: string): string {
  return TIGHT_END.test(left) ? `${left}${word}` : `${left} ${word}`
}

/** Joins operands with a connective word (かつ, または, と). Spaces separate
 * the word from anything but a corner bracket, so `x が対象である かつ …`
 * keeps its boundary and `「A」かつ「B」` stays compact. */
function connect(parts: string[], word: string): string {
  return parts.reduce((text, part) => {
    const before = BRACKET_END.test(text) ? '' : ' '
    const after = BRACKET_START.test(part) ? '' : ' '
    return `${text}${before}${word}${after}${part}`
  })
}

/** Operands that read as one unit beside かつ / または / ならば: a clause, and
 * a negation, which always ends in its own `ではない`. */
function isUnit(read: Read): boolean {
  return read.t === 'atom' || read.t === 'bot' || read.t === 'not'
}

function quoted(read: Read): string {
  return isUnit(read) ? linear(read) : `「${linear(read)}」`
}

/** `x が対象ではない` for a clause; otherwise the negated part is quoted, so
 * `φ または「ψ」ではない` never reads as negating `φ または ψ`. */
function negate(body: Read): string {
  if (body.t === 'atom' && !body.bare && body.text.endsWith('である')) return `${body.text.slice(0, -3)}ではない`
  return `「${linear(body)}」ではない`
}

/** A proposition as a modifier of the variable it binds: 「…ような x」. */
function modifier(body: Read): string {
  if (body.t === 'atom') return body.bare ? join(body.text, 'であるような') : `${body.text}ような`
  if (body.t === 'not') return `${negate(body.body)}ような`
  return `「${linear(body)}」が成り立つような`
}

function bound(domain: string, vars: string[]): string {
  return `${domain} ${vars.join('、')}`
}

function existence(unique: boolean): string {
  return unique ? 'がただ一つある' : 'がある'
}

function consequentText(read: Read): string {
  return isUnit(read) || read.t === 'forall' || read.t === 'exists' || read.t === 'binder'
    ? linear(read)
    : `「${linear(read)}」`
}

/** A binder's sentence around its body text: unquoted at the end of a prefix
 * sentence, quoted anywhere else. */
function binderText(read: Extract<Read, { t: 'binder' }>, body: string): string {
  return fillBinder(read.template, read.vars, read.template.prefix ? body : `「${body}」`)
}

function bareOrQuoted(read: Read): string {
  return (read.t === 'atom' && read.bare) || read.t === 'bot' ? linear(read) : `「${linear(read)}」`
}

function linear(read: Read): string {
  switch (read.t) {
    case 'atom': return read.text
    case 'bot': return '矛盾'
    case 'not': return negate(read.body)
    case 'and': return connect(read.items.map(quoted), 'かつ')
    case 'or': return connect(read.items.map(quoted), 'または')
    case 'imp': return `${join(connect(read.antecedents.map(quoted), 'かつ'), 'ならば')}、${consequentText(read.consequent)}`
    case 'iff': return join(connect([bareOrQuoted(read.left), bareOrQuoted(read.right)], 'と'), 'が同値である')
    case 'forall': return `すべての${bound(read.domain, read.vars)} について、${linear(read.body)}`
    case 'exists': return `${modifier(read.body)}${bound(read.domain, read.vars)} ${existence(read.unique)}`
    case 'binder': return binderText(read, linear(read.body))
  }
}

// ---------------------------------------------------------------------------
// Items for long readings

function split(read: Read): { lead: string; items: Read[] } | null {
  switch (read.t) {
    case 'and': return { lead: `次の ${read.items.length} つがすべて成り立つ`, items: read.items }
    case 'or': return { lead: `次の ${read.items.length} つのうち少なくとも 1 つが成り立つ`, items: read.items }
    case 'iff': return { lead: '次の 2 つが同値である', items: [read.left, read.right] }
    case 'imp':
      if (read.antecedents.length === 1) {
        return { lead: '① が成り立つならば、② が成り立つ', items: [read.antecedents[0], read.consequent] }
      }
      return {
        lead: `次の ${read.antecedents.length} つがすべて成り立つならば、${consequentText(read.consequent)}`,
        items: read.antecedents,
      }
    case 'forall': {
      const inner = split(read.body)
      return inner && { lead: `すべての${bound(read.domain, read.vars)} について、${inner.lead}`, items: inner.items }
    }
    case 'binder': {
      const inner = split(read.body)
      return inner && { lead: binderText(read, inner.lead), items: inner.items }
    }
    case 'exists': {
      // 「…ならば、C ような x」 does not parse; such a body stays one sentence.
      const inner = read.body.t === 'imp' || read.body.t === 'forall' ? null : split(read.body)
      return inner && {
        lead: `${inner.lead}ような${bound(read.domain, read.vars)} ${existence(read.unique)}`,
        items: inner.items,
      }
    }
    default: return null
  }
}

function quoteDepth(text: string): number {
  let depth = 0
  let deepest = 0
  for (const char of text) {
    if (char === '「') deepest = Math.max(deepest, ++depth)
    else if (char === '」') depth -= 1
  }
  return deepest
}

function layout(read: Read, splitLength: number, depth: number): ReadingBlock {
  const text = linear(read)
  if (depth <= 0 || (text.length <= splitLength && quoteDepth(text) < READING_SPLIT_QUOTE_DEPTH)) return { text }
  const parts = split(read)
  if (!parts) return { text }
  return { text: parts.lead, items: parts.items.map((item) => layout(item, splitLength, depth - 1)) }
}

/** Numbers items ①②…, falling back to (21) and above. */
export function itemMarker(index: number): string {
  return index < 20 ? String.fromCodePoint(0x2460 + index) : `(${index + 1})`
}

/** A theorem read with its premises: 「P1」と「P2」が成り立つなら、「C」が成り立つ. */
export function readTheoremSentence(premises: FormulaReading[], conclusion: FormulaReading): string {
  const c = `「${conclusion.sentence}」が成り立つ`
  if (premises.length === 0) return c
  return `${premises.map((premise) => `「${premise.sentence}」`).join('と')}が成り立つなら、${c}`
}
