import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { configApi } from './api/config'

const ReadOnlyContext = createContext(false)

export function useReadOnly(): boolean {
  return useContext(ReadOnlyContext)
}

export function ReadOnlyProvider({ children }: { children: ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
    staleTime: Infinity,
  })

  if (isLoading) {
    return <p className="p-6 text-sm text-slate-400">読み込み中…</p>
  }

  return <ReadOnlyContext.Provider value={data?.read_only ?? false}>{children}</ReadOnlyContext.Provider>
}
