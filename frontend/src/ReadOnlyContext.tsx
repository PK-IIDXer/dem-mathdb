import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { configApi } from './api/config'
import { BetaContext } from './components/BetaContext'

const ReadOnlyContext = createContext(false)

export function useReadOnly(): boolean {
  return useContext(ReadOnlyContext)
}

export function ReadOnlyProvider({ children }: { children: ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
    staleTime: Infinity,
    refetchInterval: query => query.state.data?.beta ? 30_000 : false,
  })

  if (isLoading) {
    return <p className="p-6 text-sm text-slate-400">読み込み中…</p>
  }

  return <ReadOnlyContext.Provider value={data?.read_only ?? false}><BetaContext.Provider value={data?.beta ?? null}>{children}</BetaContext.Provider></ReadOnlyContext.Provider>
}
