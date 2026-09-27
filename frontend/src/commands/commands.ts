export type CommandGroup =
  | 'palette' | 'navigation' | 'entity' | 'search' | 'formula' | 'create'
  | 'theorem' | 'metadata' | 'axiom-system' | 'step' | 'plan' | 'proof' | 'display'

export interface CommandEnvironment {
  pathname: string
  readOnly: boolean
}

export interface CommandDefinition {
  id: string
  label: string
  keywords: string[]
  group: CommandGroup
  defaultBindings: string[]
  bindingScope?: string
  when: (environment: CommandEnvironment) => boolean
  implemented?: boolean
}

const always = () => true
const writable = ({ readOnly }: CommandEnvironment) => !readOnly
const onSearch = ({ pathname }: CommandEnvironment) => ['/search', '/axioms', '/theorems', '/definitions'].includes(pathname)
const onProof = ({ pathname }: CommandEnvironment) => pathname.startsWith('/proofs/') || pathname.includes('/proofs/')

export const COMMANDS: readonly CommandDefinition[] = [
  { id: 'palette.open', label: '操作を検索', keywords: ['command', 'palette'], group: 'palette', defaultBindings: ['Mod+K', 'Mod+.'], when: always },
  { id: 'palette.close', label: '操作検索を閉じる', keywords: ['close', 'escape'], group: 'palette', defaultBindings: ['Escape'], when: always },
  { id: 'shortcuts.show', label: 'キーボードショートカットを表示', keywords: ['help', 'key'], group: 'palette', defaultBindings: ['?'], when: always },
  { id: 'navigate.home', label: 'ホームへ移動', keywords: ['home'], group: 'navigation', defaultBindings: ['g h'], when: always },
  { id: 'navigate.search', label: '検索へ移動', keywords: ['search'], group: 'navigation', defaultBindings: ['g s'], when: always },
  { id: 'navigate.symbols', label: 'Symbolsへ移動', keywords: ['symbol'], group: 'navigation', defaultBindings: ['g y'], when: always },
  { id: 'navigate.formulas', label: 'Formulasへ移動', keywords: ['formula'], group: 'navigation', defaultBindings: ['g f'], when: always },
  { id: 'navigate.axioms', label: 'Axiomsへ移動', keywords: ['axiom'], group: 'navigation', defaultBindings: ['g a'], when: always },
  { id: 'navigate.theorems', label: 'Theoremsへ移動', keywords: ['theorem'], group: 'navigation', defaultBindings: ['g t'], when: always },
  { id: 'navigate.proofs', label: 'Proofsへ移動', keywords: ['proof'], group: 'navigation', defaultBindings: ['g p'], when: always },
  { id: 'navigate.definitions', label: 'Definitionsへ移動', keywords: ['definition'], group: 'navigation', defaultBindings: ['g d'], when: always },
  ...['symbol', 'formula', 'axiom', 'axiom-system', 'theorem', 'proof', 'definition'].map((kind) => ({
    id: `open.${kind}`, label: `${kind}を開く`, keywords: [kind, 'open'], group: 'entity' as const,
    defaultBindings: [], when: always,
  })),
  { id: 'search.focus', label: '検索欄へ移動', keywords: ['find'], group: 'search', defaultBindings: ['/'], when: onSearch },
  { id: 'search.tag', label: 'タグで絞り込む', keywords: ['tag'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'search.status', label: '状態で絞り込む', keywords: ['status'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'search.clear', label: '検索条件を消去', keywords: ['clear'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'formula.focus', label: '式入力欄へ移動', keywords: ['formula', 'editor'], group: 'formula', defaultBindings: [], when: always },
  { id: 'formula.symbols', label: '記号を挿入', keywords: ['symbol', 'insert'], group: 'formula', defaultBindings: ['Mod+/'], bindingScope: 'formula-editor', when: always },
  { id: 'formula.commit', label: '式を確定', keywords: ['formula', 'register'], group: 'formula', defaultBindings: ['Mod+Enter'], bindingScope: 'formula-editor', when: writable },
  { id: 'formula.toggle-internals', label: '式の内部表現を切替', keywords: ['internals'], group: 'formula', defaultBindings: [], when: always },
  { id: 'formula.toggle-tree', label: '式の構文木を切替', keywords: ['tree'], group: 'formula', defaultBindings: [], when: always },
  ...['symbol', 'axiom', 'theorem', 'definition', 'proof'].map((kind) => ({
    id: `${kind}.create`, label: `${kind}を作成`, keywords: [kind, 'create'], group: 'create' as const,
    defaultBindings: [], when: writable,
  })),
  ...['variable.add', 'variable.remove', 'premise.add', 'premise.move', 'premise.remove', 'commit', 'proof.create'].map((action) => ({
    id: `theorem.${action}`, label: `定理: ${action}`, keywords: ['theorem', action], group: 'theorem' as const,
    defaultBindings: action === 'commit' ? ['Mod+Enter'] : [], bindingScope: action === 'commit' ? 'theorem-form' : undefined, when: writable,
  })),
  ...['description.edit', 'description.save', 'tag.add', 'tag.remove', 'symbol.display.edit', 'symbol.display.save', 'symbol.display.cancel'].map((id) => ({
    id, label: id, keywords: id.split('.'), group: 'metadata' as const, defaultBindings: [], when: writable,
  })),
  ...['create', 'open', 'add', 'remove', 'check-subset'].map((action) => ({
    id: `axiom-system.${action}`, label: `公理系: ${action}`, keywords: ['axiom', 'system', action], group: 'axiom-system' as const,
    defaultBindings: [], when: action === 'open' ? always : writable,
  })),
  ...['premise', 'assumption', 'axiom', 'theorem', 'mp', 'gen', 'imp-intro'].map((kind) => ({
    id: `step.add.${kind}`, label: `stepを追加: ${kind}`, keywords: ['step', kind], group: 'step' as const,
    defaultBindings: [], when: writable,
  })),
  { id: 'step.commit', label: 'stepを追加', keywords: ['step', 'commit'], group: 'step', defaultBindings: ['Mod+Enter'], bindingScope: 'step-form', when: writable },
  { id: 'step.accept-mp', label: 'MP候補を追加', keywords: ['step', 'mp'], group: 'step', defaultBindings: [], when: writable },
  { id: 'step.apply.rule', label: '推論定理を使う', keywords: ['step', 'rule', '推論定理'], group: 'step', defaultBindings: [], when: writable },
  { id: 'step.command-line.open', label: 'step commandを開く', keywords: ['step', 'command'], group: 'step', defaultBindings: [], when: writable, implemented: false },
  ...['hole.next', 'hole.previous', 'fill.premise', 'fill.step', 'apply.theorem', 'apply.axiom', 'recipe.choose', 'assume', 'argument.choose'].map((action) => ({
    id: `plan.${action}`, label: `plan: ${action}`, keywords: ['plan', action], group: 'plan' as const,
    defaultBindings: [], when: writable,
  })),
  { id: 'plan.apply.rule', label: '目標に推論定理を適用', keywords: ['plan', 'rule', '推論定理'], group: 'plan', defaultBindings: [], when: writable },
  { id: 'proof.validate', label: 'proofを検証', keywords: ['proof', 'validate'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'proof.view.tree', label: 'proof treeを表示', keywords: ['proof', 'tree'], group: 'proof', defaultBindings: ['v t'], when: onProof },
  { id: 'proof.view.steps', label: 'proof stepsを表示', keywords: ['proof', 'steps'], group: 'proof', defaultBindings: ['v s'], when: onProof },
  { id: 'proof.step.jump', label: 'stepへ移動', keywords: ['proof', 'step'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'proof.dependency.open', label: '依存先を開く', keywords: ['proof', 'dependency'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'explanation.close', label: '命題の説明を閉じる', keywords: ['explanation', 'close', '説明'], group: 'proof', defaultBindings: ['Escape'], bindingScope: 'proposition-explanation', when: always },
  { id: 'display.density', label: '表示密度を切替', keywords: ['display', 'density'], group: 'display', defaultBindings: [], when: always },
  { id: 'display.internals', label: '内部表示を切替', keywords: ['display', 'internals'], group: 'display', defaultBindings: [], when: always },
]

export const COMMAND_BY_ID = new Map(COMMANDS.map((command) => [command.id, command]))
