import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import { expect, it } from 'vitest'
import { ja } from './messages/ja'
import { en } from './messages/en'
import { BETA_LEGAL_COPY } from '../pages/betaLegalCopy'
import { LEGAL_COPY } from '../pages/legalCopy'
import exceptions from './literalExceptions.json'

const japanese = /[\u3040-\u30ff\u3400-\u9fff]/u
const root = path.resolve('src')
function scanLiterals(file: string, source: string) {
  const found: { file: string; kind: string; literal: string }[] = []
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true)
  function visit(node: ts.Node) {
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateHead(node)
      || ts.isTemplateMiddle(node) || ts.isTemplateTail(node) || ts.isJsxText(node) || ts.isRegularExpressionLiteral(node))
      && japanese.test(node.text)) {
      found.push({ file, kind: ts.SyntaxKind[node.kind], literal: node.getText(ast) })
    }
    ts.forEachChild(node, visit)
  }
  visit(ast)
  return found
}

function literals(file: string, source: string) {
  // A decoded Japanese character can only come from the source character or
  // a Unicode escape. Keep the full AST scan for either, including comments.
  if (!japanese.test(source) && !source.includes('\\u')) return []
  return scanLiterals(file, source)
}

it.each([
  ['const value = "日本語"', 1],
  ['const value = "\\u65e5\\u672c\\u8a9e"', 1],
  ['const value = "\\u{65e5}"', 1],
  ['const view = <p>日本語</p>', 1],
  ['const view = <input title="日本語" />', 1],
  ['const value = `日本語${count}`', 1],
  ['// 日本語のコメント\nconst value = "English"', 0],
  ['const value = "English"', 0],
  ['const value = "\\\\u65e5"', 0],
] as const)('preserves the full AST accept/reject result for %s', (source, count) => {
  const before = scanLiterals('Probe.tsx', source)
  const after = literals('Probe.tsx', source)
  expect(before).toHaveLength(count)
  expect(after).toEqual(before)
})

it('English has every Japanese key, matching functions and no Japanese except the language button', () => {
  expect(Object.keys(en).sort()).toEqual(Object.keys(ja).sort())
  for (const key of Object.keys(ja) as (keyof typeof ja)[]) {
    const value = en[key]
    expect(typeof value, key).toBe(typeof ja[key])
    const text = typeof value === 'function' ? (value as (...args: string[]) => string)('11', '22', '33') : value
    if (key === 'languageJapanese') {
      // Users must be able to recognize the Japanese language button in English.
      expect(text).toBe('日本語')
    } else expect(text, key).not.toMatch(japanese)
  }
  for (const page of [...Object.values(BETA_LEGAL_COPY), ...Object.values(LEGAL_COPY)]) {
    for (const [, text] of page.en) {
      for (const value of typeof text === 'string' ? [text] : text) expect(value).not.toMatch(japanese)
    }
    const numbers = (rows: readonly (readonly [string, string | readonly string[]])[]) => rows.flatMap(([tag, text]) => {
      if (tag !== 'h3' || typeof text !== 'string' || !/^\d+\./.test(text)) return []
      return [text.match(/^\d+/)![0]]
    })
    expect(numbers(page.en)).toEqual(numbers(page.ja))
  }
})

it('production Japanese literals exactly match the explained exception list', () => {
  const actual: ReturnType<typeof literals> = []
  function walk(directory: string) {
    for (const item of readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, item.name)
      const file = full.slice(root.length + 1).replaceAll('\\', '/')
      if (item.isDirectory()) {
        if (file !== 'test' && file !== 'i18n/messages') walk(full)
      } else if (/\.tsx?$/.test(item.name) && !item.name.includes('.test.') && !['pages/betaLegalCopy.ts', 'pages/legalCopy.ts'].includes(file)) actual.push(...literals(file, readFileSync(full, 'utf8')))
    }
  }
  walk(root)
  const sorted = (values: typeof actual) => values.map(value => JSON.stringify(value)).sort()
  expect(sorted(actual)).toEqual(sorted(exceptions.map(({ file, kind, literal, reason }) => {
    expect(reason.trim().length).toBeGreaterThan(10)
    return { file, kind, literal }
  })))
  expect(literals('Probe.tsx', 'export const Probe = () => <p>未登録の日本語</p>')).toHaveLength(1)
})
