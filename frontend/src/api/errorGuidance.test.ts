import { expect, it } from 'vitest'
import { ApiError } from './client'
import { retrySeconds } from './errorGuidance'

it.each([
  [429, 'beta.rate_limited', '17 秒'], [429, 'beta.busy', '17 秒'],
  [413, 'beta.body_too_large', '入力が大きすぎ'], [422, 'beta.limit_exceeded', '名前の文字数'],
  [422, 'formula.too_deep', '入れ子が深すぎ'], [503, 'beta.maintenance', 'メンテナンス中'],
  [503, 'beta.full', '次のリセット'], [403, 'beta.disabled', 'β では使えない'],
  [409, 'db.guard_rejected', '自分で作ったものは編集できます'],
])('explains %s / %s and a next action', (status, code, text) => {
  const error = new ApiError(Number(status), { code, limit: 'name', maximum: 120 }, '17')
  expect(error.message).toContain(text)
  expect(error.retryAfter).toBe(17)
})

it.each(['alias', 'title', 'description', 'remarks', 'formula_tokens', 'proof_steps', 'theorem_premises'])('humanizes the %s limit', limit => {
  const error = new ApiError(422, { code: 'beta.limit_exceeded', limit, maximum: 50 })
  expect(error.message).toContain('最大 50')
  expect(error.message).not.toContain(limit)
})

it.each([502, 503])('explains a non-JSON Caddy response (%s)', status => {
  expect(new ApiError(status, null).message).toContain('再読み込み')
})

it('explains a non-JSON request rejected at the proxy body limit', () => {
  expect(new ApiError(413, null).message).toContain('入力が大きすぎ')
})

it('preserves existing validation text and positions', () => {
  const error = new ApiError(422, { detail: 'existing syntax error', position: 9 })
  expect(error.message).toBe('existing syntax error')
  expect(error.position).toBe(9)
  expect(error.guidance).toBe(false)
  expect(new ApiError(422, { detail: [{ msg: 'field error' }] }).message).toBe('field error')
  expect(retrySeconds('invalid')).toBe(null)
})
