import { ja } from './messages/ja'
import { en } from './messages/en'
import { getLanguage } from './language'

export type MessageKey = keyof typeof ja
type Args<K extends MessageKey> = typeof ja[K] extends (...args: infer A) => string ? A : []

/** Pure display lookup. Never use translated text for requests or branching. */
export function t<K extends MessageKey>(key: K, ...args: Args<K>): string {
  const message = (getLanguage() === 'ja' ? ja : en)[key]
  return typeof message === 'function' ? (message as (...values: unknown[]) => string)(...args) : message
}
