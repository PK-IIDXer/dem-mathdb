import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { axiomsApi } from '../api/axioms'
import { FormulaPicker } from '../components/FormulaPicker'
import { SearchFilterBar } from '../components/SearchFilterBar'
import { ApiError } from '../api/client'
import { useReadOnly } from '../ReadOnlyContext'

export function AxiomsPage() {
  return (
    <div className="space-y-8">
      <AxiomSection />
      <AxiomSystemSection />
    </div>
  )
}

function AxiomSection() {
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([])
  const toggleTag = (tagId: number) =>
    setSelectedTagIds((prev) => (prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]))

  const { data: axioms = [] } = useQuery({
    queryKey: ['axioms', { search, tagIds: selectedTagIds }],
    queryFn: () => axiomsApi.list({ search: search || undefined, tagIds: selectedTagIds }),
  })

  const [name, setName] = useState('')
  const [formulaId, setFormulaId] = useState<number | null>(null)
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  const registerMutation = useMutation({
    mutationFn: () =>
      axiomsApi.register({
        name,
        formula_id: formulaId as number,
        description: description.trim() || undefined,
      }),
    onSuccess: (axiom) => {
      queryClient.invalidateQueries({ queryKey: ['axioms'] })
      setName('')
      setFormulaId(null)
      setDescription('')
      setError(null)
      navigate(`/axioms/${axiom.public_id}`)
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'unknown error'),
  })

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">Axioms</h2>

      {!readOnly && (
      <div className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">公理を登録</h3>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            registerMutation.mutate()
          }}
        >
          <label className="flex flex-col text-xs text-slate-500">
            name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <div>
            <div className="mb-1 text-xs text-slate-500">formula</div>
            <FormulaPicker value={formulaId} onChange={setFormulaId} />
          </div>
          <label className="flex flex-col text-xs text-slate-500">
            description (自然言語での説明)
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="例: 空集合の存在公理"
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <button
            type="submit"
            disabled={!name || formulaId == null || registerMutation.isPending}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            登録
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      </div>
      )}

      <SearchFilterBar
        search={search}
        onSearchChange={setSearch}
        selectedTagIds={selectedTagIds}
        onToggleTag={toggleTag}
      />

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">登録済みの公理 ({axioms.length})</h3>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3">id</th>
              <th className="py-1 pr-3">name / 説明 / タグ</th>
              <th className="py-1 pr-3">origin_kind</th>
            </tr>
          </thead>
          <tbody>
            {axioms.map((axiom) => (
              <tr
                key={axiom.id}
                className="border-t border-slate-100 hover:bg-slate-50"
              >
                <td className="py-1 pr-3 align-top">{axiom.id}</td>
                <td className="py-1 pr-3">
                  <Link
                    to={`/axioms/${axiom.public_id}`}
                    className="font-mono text-indigo-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                  >
                    {axiom.name}
                  </Link>
                  {axiom.description && (
                    <div className="text-xs text-slate-500">{axiom.description}</div>
                  )}
                  {axiom.tags.length > 0 && (
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {axiom.tags.map((tag) => (
                        <span
                          key={tag.id}
                          className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700"
                        >
                          {tag.name}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="py-1 pr-3 align-top text-slate-500">{axiom.origin_kind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function AxiomSystemSection() {
  const readOnly = useReadOnly()
  const queryClient = useQueryClient()
  const { data: systems = [] } = useQuery({
    queryKey: ['axiomSystems'],
    queryFn: () => axiomsApi.listSystems(),
  })
  const { data: axioms = [] } = useQuery({ queryKey: ['axioms'], queryFn: () => axiomsApi.list() })

  const [systemName, setSystemName] = useState('')
  const registerSystemMutation = useMutation({
    mutationFn: () => axiomsApi.registerSystem({ name: systemName }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['axiomSystems'] })
      setSystemName('')
    },
  })

  const [selectedSystemId, setSelectedSystemId] = useState<number | null>(null)
  const { data: members = [] } = useQuery({
    queryKey: ['axiomSystemMembers', selectedSystemId],
    queryFn: () => axiomsApi.listSystemMembers(selectedSystemId as number),
    enabled: selectedSystemId != null,
  })
  const [memberToAdd, setMemberToAdd] = useState<number | ''>('')

  const addMemberMutation = useMutation({
    mutationFn: () => axiomsApi.addSystemMember(selectedSystemId as number, Number(memberToAdd)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['axiomSystemMembers', selectedSystemId] })
      setMemberToAdd('')
    },
  })
  const removeMemberMutation = useMutation({
    mutationFn: (axiomId: number) => axiomsApi.removeSystemMember(selectedSystemId as number, axiomId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['axiomSystemMembers', selectedSystemId] })
    },
  })

  const [childId, setChildId] = useState<number | ''>('')
  const [parentId, setParentId] = useState<number | ''>('')
  const [subsetResult, setSubsetResult] = useState<boolean | null>(null)
  const checkSubsetMutation = useMutation({
    mutationFn: () => axiomsApi.isSubsetOf(Number(childId), Number(parentId)),
    onSuccess: (result) => setSubsetResult(result.is_subset),
  })

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">Axiom Systems</h2>

      {!readOnly && (
      <form
        className="flex items-end gap-2 rounded-lg border border-slate-200 p-4"
        onSubmit={(e) => {
          e.preventDefault()
          registerSystemMutation.mutate()
        }}
      >
        <label className="flex flex-col text-xs text-slate-500">
          name
          <input
            value={systemName}
            onChange={(e) => setSystemName(e.target.value)}
            required
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={!systemName || registerSystemMutation.isPending}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          公理系を登録
        </button>
      </form>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">公理系一覧 ({systems.length})</h3>
          <ul className="space-y-1 text-sm">
            {systems.map((system) => (
              <li
                key={system.id}
                className={`flex items-center justify-between rounded px-2 py-1 ${
                  selectedSystemId === system.id ? 'bg-indigo-50 font-semibold' : 'hover:bg-slate-50'
                }`}
              >
                <button
                  type="button"
                  onClick={() => setSelectedSystemId(system.id)}
                  aria-pressed={selectedSystemId === system.id}
                  className="rounded text-left hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
                >
                  #{system.id} {system.name}
                </button>
                <Link to={`/axiom-systems/${system.id}`} className="text-xs text-indigo-600 hover:underline">
                  詳細
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">メンバー管理</h3>
          {selectedSystemId == null ? (
            <p className="text-sm text-slate-400">左の一覧から公理系を選んでください</p>
          ) : (
            <div className="space-y-2">
              <ul className="space-y-1 text-sm">
                {members.map((axiom) => (
                  <li key={axiom.id} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
                    <span>
                      #{axiom.id} {axiom.name}
                    </span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => removeMemberMutation.mutate(axiom.id)}
                        className="text-slate-400 hover:text-red-600"
                      >
                        ×
                      </button>
                    )}
                  </li>
                ))}
                {members.length === 0 && <li className="text-slate-400">メンバーなし</li>}
              </ul>
              {!readOnly && (
                <div className="flex items-center gap-2">
                  <select
                    value={memberToAdd}
                    onChange={(e) => setMemberToAdd(Number(e.target.value))}
                    className="rounded border border-slate-300 px-2 py-1 text-sm"
                  >
                    <option value="" disabled>
                      追加する公理を選択…
                    </option>
                    {axioms.map((axiom) => (
                      <option key={axiom.id} value={axiom.id}>
                        #{axiom.id} {axiom.name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    disabled={memberToAdd === '' || addMemberMutation.isPending}
                    onClick={() => addMemberMutation.mutate()}
                    className="rounded bg-slate-600 px-2 py-1 text-xs text-white disabled:opacity-40"
                  >
                    追加
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">包含判定 (child ⊆ parent)</h3>
        <div className="flex items-center gap-2">
          <select
            value={childId}
            onChange={(e) => {
              setChildId(Number(e.target.value))
              setSubsetResult(null)
            }}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>
              child…
            </option>
            {systems.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
          <span className="text-slate-400">⊆</span>
          <select
            value={parentId}
            onChange={(e) => {
              setParentId(Number(e.target.value))
              setSubsetResult(null)
            }}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="" disabled>
              parent…
            </option>
            {systems.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={childId === '' || parentId === '' || checkSubsetMutation.isPending}
            onClick={() => checkSubsetMutation.mutate()}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            判定
          </button>
          {subsetResult != null && (
            <span className={`text-sm font-semibold ${subsetResult ? 'text-green-700' : 'text-red-700'}`}>
              {subsetResult ? '✓ true' : '✗ false'}
            </span>
          )}
        </div>
      </div>
    </section>
  )
}
