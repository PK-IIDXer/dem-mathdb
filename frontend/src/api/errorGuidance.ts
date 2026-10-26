export function retrySeconds(value: string | null): number | null {
  if (value == null || value.trim() === '') return null
  const seconds = /^\d+$/.test(value) ? Number(value) : Math.ceil((Date.parse(value) - Date.now()) / 1000)
  return Number.isFinite(seconds) ? Math.max(0, seconds) : null
}

export function errorGuidance(status: number, body: unknown, retry: number | null): string | null {
  const data = body && typeof body === 'object' ? body as Record<string, unknown> : null
  const code = data?.code
  if (code === 'beta.contact_unavailable') return '現在お問い合わせを保存できません。時間をおいて再試行してください。'
  if (code === 'beta.contact_invalid') return '入力内容を確認してください。本文は1〜2,000文字、対象URLは500文字、返信先は254文字までです。URLは http://、https://、/ のいずれかで始めてください。'
  if (code === 'beta.rate_limited' || code === 'beta.busy') return '混み合っているか、短時間に操作が多くなっています。' + (retry == null ? '少し待ってから再試行してください。' : `あと ${retry} 秒ほど待ってから再試行してください。`)
  if (code === 'beta.body_too_large' || (status === 413 && data == null)) return '入力が大きすぎます。入力を短くして再試行してください。'
  if (code === 'beta.limit_exceeded') {
    const labels: Record<string, string> = { name: '名前の文字数', alias: '別名の文字数', title: '名前の文字数', description: '説明の文字数', remarks: '説明の文字数', notation: 'LaTeX テンプレートの文字数', latex_template: 'LaTeX テンプレートの文字数', formula_tokens: '式の大きさ（token 数）', proof_steps: '証明の step 数', theorem_premises: '前提の数' }
    const label = typeof data?.limit === 'string' ? labels[data.limit] ?? '入力の大きさ' : '入力の大きさ'
    const maximum = typeof data?.maximum === 'number' ? `（最大 ${data.maximum}）` : ''
    return `${label}の上限${maximum}を超えています。入力を減らして再試行してください。`
  }
  if (code === 'formula.too_deep') return '式の入れ子が深すぎて処理できません。入れ子を浅くして再試行してください。'
  if (code === 'beta.maintenance') return 'メンテナンス中のため、書き込みを止めています。少し待って再読み込みしてください。'
  if (code === 'beta.full') return '容量の上限に達したため、次のリセットまで書き込めません。'
  if (code === 'beta.disabled') return 'β では使えない機能です。ほかの操作をご利用ください。'
  if (code === 'db.guard_rejected') return '基本の内容（公開済みのパッケージ）は変更できません。自分で作ったものは編集できます。'
  if ((status === 502 || status === 503) && data == null) return 'メンテナンス中です。少し待って再読み込みしてください。'
  return null
}
