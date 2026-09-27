import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { ProofStep, Symbol } from '../api/types'
import type { ReactNode } from 'react'
import { useDisplaySettings } from '../DisplaySettingsContext'

const COMFORTABLE_STEP_HEIGHT = 52
const COMPACT_STEP_HEIGHT = 32
const VISIBLE_LIST_HEIGHT = 502

export interface ProofStepListHandle {
  scrollToOrd: (ord: number) => void
}

interface ProofStepListProps {
  proofId: number
  steps: ProofStep[]
  highlightOrd: number | null
  renderFormula: (step: ProofStep) => ReactNode
  renderJustification: (step: ProofStep, symbolsById: Map<number, Symbol>) => ReactNode
  symbolsById: Map<number, Symbol>
  onUseRule?: (ord: number) => void
}

/** A variable-height virtual list for proof steps.
 *
 * Only the visible rows plus a small overscan are mounted, which bounds KaTeX
 * work for generated proofs with hundreds of conclusions.  Rows report their
 * measured height back to the virtualizer so wrapped justifications remain
 * aligned while scrolling.
 */
export const ProofStepList = forwardRef<ProofStepListHandle, ProofStepListProps>(
  function ProofStepList(
    { proofId, steps, highlightOrd, renderFormula, renderJustification, symbolsById, onUseRule },
    ref,
  ) {
    const { density } = useDisplaySettings()
    const estimatedStepHeight = density === 'compact' ? COMPACT_STEP_HEIGHT : COMFORTABLE_STEP_HEIGHT
    const scrollRef = useRef<HTMLDivElement>(null)
    const indexByOrd = useMemo(
      () => new Map(steps.map((step, index) => [step.ord, index])),
      [steps],
    )
    const virtualizer = useVirtualizer({
      count: steps.length,
      getScrollElement: () => scrollRef.current,
      estimateSize: () => estimatedStepHeight,
      getItemKey: (index) => steps[index]?.ord ?? index,
      overscan: 6,
      initialRect: { width: 960, height: VISIBLE_LIST_HEIGHT },
    })

    useImperativeHandle(ref, () => ({
      scrollToOrd(ord: number) {
        const index = indexByOrd.get(ord)
        if (index != null) virtualizer.scrollToIndex(index, { align: 'center' })
      },
    }), [indexByOrd, virtualizer])

    if (steps.length === 0) {
      return (
        <ol className="rounded-lg border border-slate-200">
          <li className="px-3 py-2 text-xs text-slate-400">まだステップがありません</li>
        </ol>
      )
    }

    return (
      <div
        ref={scrollRef}
        data-testid="proof-step-list"
        data-density={density}
        className="max-h-[70vh] overflow-auto rounded-lg border border-slate-200"
      >
        <ol className="relative" style={{ height: `${virtualizer.getTotalSize()}px` }}>
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const step = steps[virtualRow.index]
            return (
              <li
                key={step.ord}
                ref={virtualizer.measureElement}
                data-index={virtualRow.index}
                id={`proof-${proofId}-step-${step.ord}`}
                className={`absolute left-0 top-0 flex min-h-8 w-full flex-wrap items-baseline border-b border-slate-100 px-3 transition-colors ${
                  density === 'compact' ? 'gap-x-2 gap-y-0 py-1' : 'gap-x-3 gap-y-1 py-2'
                } ${
                  highlightOrd === step.ord ? 'bg-amber-50' : 'bg-white'
                }`}
                style={{ transform: `translateY(${virtualRow.start}px)` }}
              >
                <span className="w-8 shrink-0 text-xs text-slate-400">({step.ord})</span>
                <span className="min-w-0 max-w-full break-words text-sm">{renderFormula(step)}</span>
                <span className="ml-auto text-xs text-slate-500">
                  {renderJustification(step, symbolsById)}
                </span>
                {onUseRule && <button type="button" onClick={() => onUseRule(step.ord)} className="text-xs text-indigo-700 hover:underline">この step に推論定理を使う</button>}
              </li>
            )
          })}
        </ol>
      </div>
    )
  },
)
