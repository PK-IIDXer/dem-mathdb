import { t } from "../i18n/translate"
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
  { id: 'palette.open', get label() { return t("CommandPalette_040") }, keywords: ['command', 'palette'], group: 'palette', defaultBindings: ['Mod+K', 'Mod+.'], when: always },
  { id: 'palette.close', get label() { return t("commands_050") }, keywords: ['close', 'escape'], group: 'palette', defaultBindings: ['Escape'], when: always },
  { id: 'shortcuts.show', get label() { return t("commands_051") }, keywords: ['help', 'key'], group: 'palette', defaultBindings: ['?'], when: always },
  { id: 'navigate.home', get label() { return t("commands_052") }, keywords: ['home'], group: 'navigation', defaultBindings: ['g h'], when: always },
  { id: 'navigate.search', get label() { return t("commands_053") }, keywords: ['search'], group: 'navigation', defaultBindings: ['g s'], when: always },
  { id: 'navigate.symbols', get label() { return t("commands_054") }, keywords: ['symbol'], group: 'navigation', defaultBindings: ['g y'], when: always },
  { id: 'navigate.formulas', get label() { return t("commands_055") }, keywords: ['formula'], group: 'navigation', defaultBindings: ['g f'], when: always },
  { id: 'navigate.axioms', get label() { return t("commands_056") }, keywords: ['axiom'], group: 'navigation', defaultBindings: ['g a'], when: always },
  { id: 'navigate.theorems', get label() { return t("commands_057") }, keywords: ['theorem'], group: 'navigation', defaultBindings: ['g t'], when: always },
  { id: 'navigate.proofs', get label() { return t("commands_058") }, keywords: ['proof'], group: 'navigation', defaultBindings: ['g p'], when: always },
  { id: 'navigate.definitions', get label() { return t("commands_059") }, keywords: ['definition'], group: 'navigation', defaultBindings: ['g d'], when: always },
  ...['symbol', 'formula', 'axiom', 'axiom-system', 'theorem', 'proof', 'definition'].map((kind) => ({
    id: `open.${kind}`, get label() { return t("commands_060", kind) }, keywords: [kind, 'open'], group: 'entity' as const,
    defaultBindings: [], when: always,
  })),
  { id: 'search.focus', get label() { return t("commands_061") }, keywords: ['find'], group: 'search', defaultBindings: ['/'], when: onSearch },
  { id: 'search.tag', get label() { return t("commands_062") }, keywords: ['tag'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'search.status', get label() { return t("commands_063") }, keywords: ['status'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'search.clear', get label() { return t("commands_064") }, keywords: ['clear'], group: 'search', defaultBindings: [], when: onSearch },
  { id: 'formula.focus', get label() { return t("commands_065") }, keywords: ['formula', 'editor'], group: 'formula', defaultBindings: [], when: always },
  { id: 'formula.symbols', get label() { return t("commands_066") }, keywords: ['symbol', 'insert'], group: 'formula', defaultBindings: ['Mod+/'], bindingScope: 'formula-editor', when: always },
  { id: 'formula.commit', get label() { return t("commands_067") }, keywords: ['formula', 'register'], group: 'formula', defaultBindings: ['Mod+Enter'], bindingScope: 'formula-editor', when: writable },
  { id: 'formula.toggle-internals', get label() { return t("commands_068") }, keywords: ['internals'], group: 'formula', defaultBindings: [], when: always },
  { id: 'formula.toggle-tree', get label() { return t("commands_069") }, keywords: ['tree'], group: 'formula', defaultBindings: [], when: always },
  ...['symbol', 'axiom', 'theorem', 'definition', 'proof'].map((kind) => ({
    id: `${kind}.create`, get label() { return t("commands_070", kind) }, keywords: [kind, 'create'], group: 'create' as const,
    defaultBindings: [], when: writable,
  })),
  ...['variable.add', 'variable.remove', 'premise.add', 'premise.move', 'premise.remove', 'commit', 'proof.create'].map((action) => ({
    id: `theorem.${action}`, get label() { return t("commands_071", action) }, keywords: ['theorem', action], group: 'theorem' as const,
    defaultBindings: action === 'commit' ? ['Mod+Enter'] : [], bindingScope: action === 'commit' ? 'theorem-form' : undefined, when: writable,
  })),
  ...['description.edit', 'description.save', 'tag.add', 'tag.remove', 'symbol.display.edit', 'symbol.display.save', 'symbol.display.cancel'].map((id) => ({
    id, label: id, keywords: id.split('.'), group: 'metadata' as const, defaultBindings: [], when: writable,
  })),
  ...['create', 'open', 'add', 'remove', 'check-subset'].map((action) => ({
    id: `axiom-system.${action}`, get label() { return t("commands_072", action) }, keywords: ['axiom', 'system', action], group: 'axiom-system' as const,
    defaultBindings: [], when: action === 'open' ? always : writable,
  })),
  ...['premise', 'assumption', 'axiom', 'theorem', 'mp', 'gen', 'imp-intro'].map((kind) => ({
    id: `step.add.${kind}`, get label() { return t("commands_073", kind) }, keywords: ['step', kind], group: 'step' as const,
    defaultBindings: [], when: writable,
  })),
  { id: 'step.commit', get label() { return t("commands_074") }, keywords: ['step', 'commit'], group: 'step', defaultBindings: ['Mod+Enter'], bindingScope: 'step-form', when: writable },
  { id: 'step.accept-mp', get label() { return t("commands_075") }, keywords: ['step', 'mp'], group: 'step', defaultBindings: [], when: writable },
  { id: 'step.apply.rule', get label() { return t("commands_076") }, keywords: ['step', 'rule', '推論定理'], group: 'step', defaultBindings: [], when: writable },
  { id: 'step.command-line.open', get label() { return t("commands_078") }, keywords: ['step', 'command'], group: 'step', defaultBindings: [], when: writable, implemented: false },
  ...['hole.next', 'hole.previous', 'fill.premise', 'fill.step', 'apply.theorem', 'apply.axiom', 'recipe.choose', 'assume', 'argument.choose'].map((action) => ({
    id: `plan.${action}`, label: `plan: ${action}`, keywords: ['plan', action], group: 'plan' as const,
    defaultBindings: [], when: writable,
  })),
  { id: 'plan.apply.rule', get label() { return t("commands_079") }, keywords: ['plan', 'rule', '推論定理'], group: 'plan', defaultBindings: [], when: writable },
  { id: 'proof.validate', get label() { return t("commands_081") }, keywords: ['proof', 'validate'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'proof.view.tree', get label() { return t("commands_082") }, keywords: ['proof', 'tree'], group: 'proof', defaultBindings: ['v t'], when: onProof },
  { id: 'proof.view.steps', get label() { return t("commands_083") }, keywords: ['proof', 'steps'], group: 'proof', defaultBindings: ['v s'], when: onProof },
  { id: 'proof.step.jump', get label() { return t("commands_084") }, keywords: ['proof', 'step'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'proof.dependency.open', get label() { return t("commands_085") }, keywords: ['proof', 'dependency'], group: 'proof', defaultBindings: [], when: onProof },
  { id: 'explanation.close', get label() { return t("commands_086") }, keywords: ['explanation', 'close', '説明'], group: 'proof', defaultBindings: ['Escape'], bindingScope: 'proposition-explanation', when: always },
  { id: 'display.density', get label() { return t("commands_088") }, keywords: ['display', 'density'], group: 'display', defaultBindings: [], when: always },
  { id: 'display.internals', get label() { return t("commands_089") }, keywords: ['display', 'internals'], group: 'display', defaultBindings: [], when: always },
]

export const COMMAND_BY_ID = new Map(COMMANDS.map((command) => [command.id, command]))
