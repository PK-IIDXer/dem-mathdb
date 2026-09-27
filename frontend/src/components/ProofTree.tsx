import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { FormulaPreview } from './FormulaPreview'
import { PropositionExplanation } from './PropositionExplanation'
import { buildProofTree, proofTreeRuleLabel, type ProofTreeNode } from './proofTreeModel'
import type { LemmaDependency, ProofStep, Symbol } from '../api/types'

interface ProofTreeProps {
  proofId: number
  steps: ProofStep[]
  onSelectStep?: (ord: number) => void
  symbolsById: Map<number, Symbol>
  lemmas: Map<number, LemmaDependency>
}

export function ProofTree({ proofId, steps, onSelectStep, symbolsById, lemmas }: ProofTreeProps) {
  const tree = useMemo(() => buildProofTree(steps), [steps])
  const exportRef = useRef<HTMLDivElement>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState(false)

  async function downloadSvg() {
    if (!exportRef.current) return
    setIsExporting(true)
    setExportError(null)
    try {
      await document.fonts.ready
      const svg = renderElementToSvg(exportRef.current)
      const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))
      const link = document.createElement('a')
      link.download = `proof-${proofId}-tree.svg`
      link.href = url
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      setExportError(error instanceof Error ? error.message : '画像を書き出せませんでした')
    } finally {
      setIsExporting(false)
    }
  }

  if (!tree.root) {
    return <p className="rounded-lg border border-slate-200 px-3 py-4 text-sm text-slate-400">まだステップがありません</p>
  }

  return (
    <div className="space-y-2">
      <div className="proof-tree-controls flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={downloadSvg}
          disabled={isExporting}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {isExporting ? '画像を作成中…' : 'SVG画像をダウンロード'}
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          PDFとして印刷
        </button>
        <span className="text-xs text-slate-400">PDFは印刷画面で「PDFに保存」を選択してください。</span>
      </div>

      {exportError && <p className="text-xs text-red-700">{exportError}</p>}

      <div id="proof-tree-print-area" className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <div ref={exportRef} className="proof-tree-canvas">
          <ProofTreeNodeView node={tree.root} onSelectStep={onSelectStep} symbolsById={symbolsById} lemmas={lemmas} />
        </div>
      </div>

      {tree.omittedStepOrds.length > 0 && (
        <p className="text-xs text-slate-400">
          最終ステップから参照されないステップ ({tree.omittedStepOrds.join(', ')}) は証明図から省略しています。
        </p>
      )}
    </div>
  )
}

function ProofTreeNodeView({
  node,
  onSelectStep,
  symbolsById,
  lemmas,
}: {
  node: ProofTreeNode
  onSelectStep?: (ord: number) => void
  symbolsById: Map<number, Symbol>
  lemmas: Map<number, LemmaDependency>
}) {
  const label = proofTreeRuleLabel(node)
  const nodeRef = useRef<HTMLDivElement>(null)
  const conclusionRef = useRef<HTMLDivElement>(null)
  const labelRef = useRef<HTMLSpanElement>(null)
  const premiseKey = node.children.map((child) => child.step.ord).join(',')

  useLayoutEffect(() => {
    const nodeElement = nodeRef.current
    const conclusionElement = conclusionRef.current
    const labelElement = labelRef.current
    if (!nodeElement || !conclusionElement || !labelElement) return
    const directPremiseSelector =
      ':scope > .proof-tree-premises > .proof-tree-node > .proof-tree-conclusion > .proof-tree-formula'

    function updateLayout() {
      if (!nodeElement || !conclusionElement || !labelElement) return
      const conclusionRect = conclusionElement.getBoundingClientRect()
      let left = conclusionRect.left
      let right = conclusionRect.right

      const premiseFormulas = nodeElement.querySelectorAll<HTMLElement>(directPremiseSelector)
      for (const formula of premiseFormulas) {
        const formulaRect = formula.getBoundingClientRect()
        left = Math.min(left, formulaRect.left)
        right = Math.max(right, formulaRect.right)
      }

      conclusionElement.style.setProperty('--proof-line-left', `${left - conclusionRect.left}px`)
      conclusionElement.style.setProperty('--proof-line-width', `${right - left}px`)

      // The label is absolutely positioned beside the inference line. Reserve
      // exactly the portion that protrudes beyond this node so the following
      // sibling proof cannot overlap it.
      const nodeRect = nodeElement.getBoundingClientRect()
      const labelRect = labelElement.getBoundingClientRect()
      const clearance = Math.max(0, labelRect.right - nodeRect.right + 8)
      const currentClearance = Number.parseFloat(
        nodeElement.style.getPropertyValue('--proof-label-clearance') || '0',
      )
      if (Math.abs(clearance - currentClearance) >= 0.5) {
        nodeElement.style.setProperty('--proof-label-clearance', `${clearance}px`)
      }
    }

    updateLayout()
    const observer = new ResizeObserver(updateLayout)
    observer.observe(nodeElement)
    observer.observe(labelElement)
    const ownFormula = conclusionElement.querySelector<HTMLElement>(':scope > .proof-tree-formula')
    if (ownFormula) observer.observe(ownFormula)
    for (const formula of nodeElement.querySelectorAll<HTMLElement>(directPremiseSelector)) {
      observer.observe(formula)
    }
    return () => observer.disconnect()
  }, [node.step.ord, premiseKey])

  return (
    <div ref={nodeRef} className="proof-tree-node">
      {node.children.length > 0 && (
        <div className="proof-tree-premises">
          {node.children.map((child, index) => (
            <ProofTreeNodeView
              key={`${child.step.ord}-${index}`}
              node={child}
              onSelectStep={onSelectStep}
              symbolsById={symbolsById}
              lemmas={lemmas}
            />
          ))}
        </div>
      )}
      {node.isReference && <div className="proof-tree-source">⋮ (ステップ {node.step.ord})</div>}
      {node.step.step_kind === 'theorem' && node.children.length === 0 && !node.isReference && (
        <div className="proof-tree-source">⋮ (Proof #{node.step.applied_proof_id})</div>
      )}
      <div ref={conclusionRef} className="proof-tree-conclusion">
        <span className="proof-tree-inference-line" aria-hidden="true" />
        <span ref={labelRef} className="proof-tree-rule-label">({label})</span>
        <button
          type="button"
          title={
            node.isDischarged
              ? `ステップ (${node.step.ord}) を一覧で表示（解消済みの仮定）`
              : `ステップ (${node.step.ord}) を一覧で表示`
          }
          onClick={() => onSelectStep?.(node.step.ord)}
          className="proof-tree-formula"
        >
          {node.isDischarged && <span className="proof-tree-bracket">[</span>}
          <FormulaPreview formulaId={node.step.conclusion_formula.id} showTextPreview={false} />
          {node.isDischarged && <span className="proof-tree-bracket">]</span>}
        </button>
        <PropositionExplanation step={node.step} symbolsById={symbolsById} lemmas={lemmas}
          trigger="説明" onShowInList={onSelectStep} className="proof-tree-explanation ml-2 text-xs text-indigo-700 hover:underline" />
        <sub className="proof-tree-step-number">({node.step.ord})</sub>
      </div>
    </div>
  )
}

function renderElementToSvg(element: HTMLElement): string {
  const width = Math.ceil(element.scrollWidth)
  const height = Math.ceil(element.scrollHeight)
  if (width === 0 || height === 0) throw new Error('空の証明図は書き出せません')

  const clone = element.cloneNode(true) as HTMLElement
  clone.style.width = `${width}px`
  clone.style.height = `${height}px`
  clone.style.margin = '0'

  // KaTeX includes an accessible MathML representation beside its HTML/font
  // rendering. Use that native MathML in the standalone SVG so the downloaded
  // image does not depend on KaTeX web-font files or the application's CSS.
  for (const katex of clone.querySelectorAll('.katex')) {
    const math = katex.querySelector('.katex-mathml math')
    if (math) katex.replaceChildren(math.cloneNode(true))
  }

  const serialized = new XMLSerializer().serializeToString(clone)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml"><style>${EXPORT_STYLES}</style>${serialized}</div></foreignObject></svg>`
}

const EXPORT_STYLES = `
* { box-sizing: border-box; }
.proof-tree-canvas { display: inline-flex; min-width: 100%; justify-content: center; padding: 40px 64px; color: #1e293b; background: #fff; font-family: serif; }
.proof-tree-node { display: inline-flex; flex: 0 0 auto; flex-direction: column; align-items: center; justify-content: flex-end; margin-right: var(--proof-label-clearance, 0px); }
.proof-tree-premises { display: flex; align-items: flex-end; justify-content: center; gap: 64px; padding-bottom: 18px; }
.proof-tree-source { margin-bottom: 6px; color: #64748b; font: 12px sans-serif; white-space: nowrap; }
.proof-tree-conclusion { --proof-line-left: 0px; --proof-line-width: 100%; position: relative; display: flex; min-width: 112px; align-items: baseline; justify-content: center; padding: 9px 14px 0; }
.proof-tree-inference-line { position: absolute; left: var(--proof-line-left); top: 0; width: var(--proof-line-width); border-top: 1.5px solid #334155; }
.proof-tree-rule-label { position: absolute; left: calc(var(--proof-line-left) + var(--proof-line-width) + 6px); top: -12px; color: #475569; font: 11px/16px sans-serif; white-space: nowrap; }
.proof-tree-formula { cursor: default; border: 0; padding: 0; background: transparent; color: inherit; font-size: 15px; white-space: nowrap; }
.proof-tree-bracket { padding: 0 1px; color: inherit; font-size: 15px; }
.proof-tree-formula math { font-size: 1.05em; }
.proof-tree-explanation { display: none; }
.proof-tree-step-number { position: static; margin-left: 3px; color: #94a3b8; font: 10px/1 sans-serif; white-space: nowrap; transform: translateY(0.3em); }
`
