import { useCallback } from 'react'
import { NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { ReadOnlyProvider, useReadOnly } from './ReadOnlyContext'
import { HomePage } from './pages/HomePage'
import { SymbolsPage } from './pages/SymbolsPage'
import { SymbolDetailPage } from './pages/SymbolDetailPage'
import { FormulasPage } from './pages/FormulasPage'
import { AxiomsPage } from './pages/AxiomsPage'
import { AxiomDetailPage } from './pages/AxiomDetailPage'
import { AxiomSystemDetailPage } from './pages/AxiomSystemDetailPage'
import { TheoremsPage } from './pages/TheoremsPage'
import { TheoremDetailPage } from './pages/TheoremDetailPage'
import { ProofsPage } from './pages/ProofsPage'
import { ProofPage } from './pages/ProofPage'
import { DefinitionsPage } from './pages/DefinitionsPage'
import { DefinitionDetailPage } from './pages/DefinitionDetailPage'
import { TheoremSearchPage } from './pages/TheoremSearchPage'
import { PrivacyPolicyPage } from './pages/PrivacyPolicyPage'
import { DisclaimerPage } from './pages/DisclaimerPage'
import { CommandProvider, useCommand } from './commands/CommandProvider'
import { CommandPalette } from './commands/CommandPalette'
import { ShortcutHelp } from './commands/ShortcutHelp'
import { DisplaySettingsProvider } from './DisplaySettingsContext'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-3 py-1.5 text-sm font-medium ${
    isActive ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'
  }`

function App() {
  return (
    <ReadOnlyProvider>
      <CommandProvider>
        <DisplaySettingsProvider>
          <AppShell />
        </DisplaySettingsProvider>
      </CommandProvider>
    </ReadOnlyProvider>
  )
}

function AppShell() {
  const readOnly = useReadOnly()
  const navigate = useNavigate()
  const navigateFromCommand = useCallback((path: string) => {
    navigate(path)
    window.setTimeout(() => document.querySelector<HTMLElement>('main')?.focus(), 0)
  }, [navigate])
  useCommand('navigate.home', () => navigateFromCommand('/'))
  useCommand('navigate.search', () => navigateFromCommand('/search'))
  useCommand('navigate.symbols', () => navigateFromCommand('/symbols'))
  useCommand('navigate.formulas', () => navigateFromCommand('/formulas'))
  useCommand('navigate.axioms', () => navigateFromCommand('/axioms'))
  useCommand('navigate.theorems', () => navigateFromCommand('/theorems'))
  useCommand('navigate.proofs', () => navigateFromCommand('/proofs'))
  useCommand('navigate.definitions', () => navigateFromCommand('/definitions'))
  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold text-slate-900">数学DB(仮)</h1>
          {readOnly && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
              閲覧専用モード
            </span>
          )}
        </div>
        <nav className="flex items-center gap-2">
          <NavLink to="/" end className={navLinkClass}>
            ホーム
          </NavLink>
          <NavLink to="/search" className={navLinkClass}>
            検索
          </NavLink>
          <NavLink to="/symbols" className={navLinkClass}>
            Symbols
          </NavLink>
          <NavLink to="/formulas" className={navLinkClass}>
            Formulas
          </NavLink>
          <NavLink to="/axioms" className={navLinkClass}>
            Axioms
          </NavLink>
          <NavLink to="/theorems" className={navLinkClass}>
            Theorems
          </NavLink>
          <NavLink to="/proofs" className={navLinkClass}>
            Proofs
          </NavLink>
          <NavLink to="/definitions" className={navLinkClass}>
            Definitions
          </NavLink>
          <CommandPalette />
        </nav>
      </header>
      <main tabIndex={-1}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/symbols" element={<SymbolsPage />} />
          <Route path="/symbols/:id" element={<SymbolDetailPage />} />
          <Route path="/formulas" element={<FormulasPage />} />
          <Route path="/axioms" element={<AxiomsPage />} />
          <Route path="/axioms/:id" element={<AxiomDetailPage />} />
          <Route path="/axiom-systems/:id" element={<AxiomSystemDetailPage />} />
          <Route path="/theorems" element={<TheoremsPage />} />
          <Route path="/theorems/:id" element={<TheoremDetailPage />} />
          <Route path="/theorems/:id/proofs/:proofId" element={<TheoremDetailPage />} />
          <Route path="/proofs" element={<ProofsPage />} />
          <Route path="/proofs/:id" element={<ProofPage />} />
          <Route path="/definitions" element={<DefinitionsPage />} />
          <Route path="/definitions/:id" element={<DefinitionDetailPage />} />
          <Route path="/search" element={<TheoremSearchPage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/disclaimer" element={<DisclaimerPage />} />
        </Routes>
      </main>
      <ShortcutHelp />
      <footer className="mt-10 flex justify-center gap-4 border-t border-slate-200 pt-4 text-xs text-slate-400">
        <NavLink to="/privacy" className="hover:underline">
          プライバシーポリシー
        </NavLink>
        <NavLink to="/disclaimer" className="hover:underline">
          免責事項
        </NavLink>
      </footer>
    </div>
  )
}

export default App
