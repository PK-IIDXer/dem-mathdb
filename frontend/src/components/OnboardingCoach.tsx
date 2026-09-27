import type { ReactNode } from 'react'

export function OnboardingCoach({ step, title, children }: {
  step: 1 | 2 | 3
  title: string
  children: ReactNode
}) {
  return (
    <aside className="fixed bottom-5 right-5 z-30 w-[min(24rem,calc(100vw-2.5rem))] rounded-xl border border-indigo-300 bg-white p-4 shadow-xl">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-indigo-950">{title}</h2>
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700">
          {step} / 3
        </span>
      </div>
      <div className="space-y-2 text-sm leading-6 text-slate-700">{children}</div>
    </aside>
  )
}
