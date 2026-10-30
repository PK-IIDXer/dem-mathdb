import { vi } from 'vitest'
import componentApi from './fixtures/i18n-tutorial.json'
const fixture = componentApi
const requestUrl = (input: RequestInfo | URL) => typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function currentProofPayload(stepPosts: number, verified: boolean) {
  const onboarding = fixture.onboarding
  if (verified) return onboarding.verified
  if (stepPosts >= 5) return { ...onboarding.after_first_mp, steps: onboarding.verified.steps.slice(0, stepPosts) }
  if (stepPosts >= 4) return onboarding.after_first_mp
  if (stepPosts >= 3) return onboarding.after_axioms
  if (stepPosts > 0) return { ...onboarding.after_axioms, steps: onboarding.after_axioms.steps.slice(0, stepPosts), followups: [] }
  return onboarding.draft
}

export function createOnboardingFetch(betaEnabled = false) {
  const onboarding = fixture.onboarding
  let proofCreated = false
  let stepPosts = 0
  let verified = false

  return vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input)
    const method = init?.method ?? 'GET'
    const path = url.replace(/^\/api/, '')
    const proofPayload = currentProofPayload(stepPosts, verified)

    if (method === 'GET' && path === '/config') return Promise.resolve(jsonResponse(betaEnabled ? { ...onboarding.config, beta: { enabled: true, write_state: 'open', next_reset_at: null, last_reset_at: null, last_reset_error: null, limits: {} } } : onboarding.config))
    if (method === 'GET' && path === '/workspace/info') return Promise.resolve(jsonResponse({ title: 'Tutorial fixture', local_namespace_name: onboarding.theorem.namespace_name }))
    if (method === 'GET' && path === '/formula-types') return Promise.resolve(jsonResponse(onboarding.formula_types))
    if (method === 'GET' && path === '/symbol-aliases') return Promise.resolve(jsonResponse(onboarding.symbol_aliases))
    if (method === 'GET' && path.startsWith('/symbols')) return Promise.resolve(jsonResponse(onboarding.symbols))
    if (method === 'GET' && path === '/formulas') return Promise.resolve(jsonResponse(onboarding.formulas))
    if (method === 'GET' && path === `/formulas/${onboarding.goal.id}`) return Promise.resolve(jsonResponse(onboarding.goal))
    if (method === 'GET' && /^\/formulas\/\d+$/.test(path)) {
      const id = Number(path.split('/').at(-1))
      const formula = onboarding.verified.formulas.find(item => item.id === id)
      if (formula) return Promise.resolve(jsonResponse(formula))
    }
    if (method === 'GET' && path === '/tags') return Promise.resolve(jsonResponse(onboarding.tags))
    if (method === 'GET' && path.startsWith('/theorems?')) return Promise.resolve(jsonResponse(onboarding.theorems))
    if (method === 'GET' && path === '/theorems') return Promise.resolve(jsonResponse(onboarding.theorems))
    if (method === 'GET' && path === `/theorems/${onboarding.theorem.id}/premises`) return Promise.resolve(jsonResponse(onboarding.theorem_premises))
    if (method === 'GET' && path === `/theorems/${onboarding.theorem.id}/used-in-theorems`) return Promise.resolve(jsonResponse(onboarding.theorem_used_in))
    if (method === 'GET' && path === `/theorems/${onboarding.theorem.id}/proofs`) return Promise.resolve(jsonResponse(proofCreated ? onboarding.proofs : []))
    if (method === 'GET' && (path === `/theorems/${onboarding.theorem.id}` || path === `/theorems/${onboarding.theorem.public_id}`)) return Promise.resolve(jsonResponse(onboarding.theorem))
    if (method === 'GET' && path === '/axioms') return Promise.resolve(jsonResponse(onboarding.axioms))
    if (method === 'GET' && path === '/axiom-systems') return Promise.resolve(jsonResponse(onboarding.axiom_systems))
    if (method === 'GET' && path.startsWith('/axioms/by-name/')) {
      const name = decodeURIComponent(path.slice('/axioms/by-name/'.length))
      const item = onboarding.axiom_workflow.find((entry) => entry.name === name)
      if (!item) throw new Error(`missing recorded axiom ${name}`)
      return Promise.resolve(jsonResponse(item.axiom))
    }
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}`) return Promise.resolve(jsonResponse(verified ? onboarding.verified.proof : onboarding.proof))
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}/steps`) return Promise.resolve(jsonResponse(proofPayload.steps))
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}/state`) return Promise.resolve(jsonResponse(proofPayload.state))
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}/formulas`) return Promise.resolve(jsonResponse(proofPayload.formulas))
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}/used-axioms`) return Promise.resolve(jsonResponse(onboarding.verified.used_axioms))
    if (method === 'GET' && path === `/proofs/${onboarding.proof.id}/direct-dependencies`) return Promise.resolve(jsonResponse({ axioms: onboarding.verified.used_axioms, lemmas: [], applied_proofs: {}, applied_proof_public_ids: {} }))
    if (method === 'GET' && path.endsWith('/steps/2/followups')) return Promise.resolve(jsonResponse(onboarding.after_axioms.followups))
    if (method === 'GET' && path.endsWith('/steps/3/followups')) return Promise.resolve(jsonResponse(onboarding.after_first_mp.followups))

    if (method === 'POST' && path === '/formulas/parse') {
      const body = JSON.parse(String(init?.body)) as { text: string }
      if (body.text === 'forall x. P(x) -> P(x)') return Promise.resolve(jsonResponse(onboarding.goal_parse))
      const index = body.text.startsWith('(P(x) ->') ? 2 : body.text.includes('((P(x) -> P(x))') ? 0 : 1
      const recorded = onboarding.axiom_workflow[index]
      if (!recorded) throw new Error(`missing recorded parse response for ${body.text}`)
      return Promise.resolve(jsonResponse(recorded.parse))
    }
    if (method === 'POST' && path === '/formulas/print') return Promise.resolve(jsonResponse(onboarding.goal_print))
    if (method === 'POST' && path === '/formulas') return Promise.resolve(jsonResponse(onboarding.goal, 201))
    if (method === 'POST' && path === '/tags') return Promise.resolve(jsonResponse(onboarding.tag, 201))
    if (method === 'POST' && path === '/theorems') return Promise.resolve(jsonResponse(onboarding.theorem, 201))
    if (method === 'POST' && path === '/proofs') {
      proofCreated = true
      return Promise.resolve(jsonResponse(onboarding.proof, 201))
    }
    if (method === 'POST' && path.endsWith('/steps/suggest')) {
      const body = JSON.parse(String(init?.body))
      const recorded = onboarding.axiom_workflow.find(item => JSON.stringify(item.parse.tokens) === JSON.stringify(body.goal_tokens))
      if (!recorded) throw new Error('missing recorded suggestion response')
      return Promise.resolve(jsonResponse(recorded.suggestion))
    }
    if (method === 'POST' && path === `/proofs/${onboarding.proof.id}/steps`) {
      const responses = [
        ...onboarding.axiom_workflow.map((entry) => entry.step),
        onboarding.first_mp,
        onboarding.second_mp,
        onboarding.gen_step,
      ]
      const response = responses[stepPosts]
      if (!response) throw new Error('unexpected extra proof step')
      stepPosts += 1
      return Promise.resolve(jsonResponse(response, 201))
    }
    if (method === 'POST' && path === `/proofs/${onboarding.proof.id}/validate`) {
      verified = true
      return Promise.resolve(jsonResponse(onboarding.validate))
    }
    throw new Error(`unhandled onboarding request: ${method} ${path}`)
  })
}
