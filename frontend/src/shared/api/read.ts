/**
 * Small readers for the body of a successful response.
 *
 * TypeScript only knows what I tell it about a body that came over the network.
 * These helpers check the shape at the boundary, one field at a time, so a
 * response that breaks the contract fails here with the name of the field and
 * the endpoint, and not later as `undefined` in the middle of a screen.
 *
 * Every helper throws an `ApiError` of kind `malformed`. None returns null to
 * mean failure.
 */

import { asRecord, malformedResponse, requireField } from '../api-problem'
import type { Money } from './contract'

/** Money on the wire. Digits, a point, and exactly two decimals. */
const MONEY_PATTERN = /^\d+\.\d{2}$/

/** Read a value that must be a JSON object. */
export function readObject(
  value: unknown,
  requestPath: string,
  what: string,
): Record<string, unknown> {
  const record = asRecord(value)
  if (!record) throw malformedResponse(requestPath, `Expected ${what} from ${requestPath}.`)
  return record
}

/** Read a field that must be a string. */
export function readText(source: Record<string, unknown>, key: string, requestPath: string): string {
  return requireField<string>(source, key, 'string', requestPath)
}

/** Read a field the contract allows to be null. A missing field is not null. */
export function readNullableText(
  source: Record<string, unknown>,
  key: string,
  requestPath: string,
): string | null {
  return source[key] === null ? null : readText(source, key, requestPath)
}

/** Read a field that must be true or false. */
export function readFlag(source: Record<string, unknown>, key: string, requestPath: string): boolean {
  return requireField<boolean>(source, key, 'boolean', requestPath)
}

/** Read a whole number that is zero or more, such as a count or a page. */
export function readCount(source: Record<string, unknown>, key: string, requestPath: string): number {
  const value = requireField<number>(source, key, 'number', requestPath)
  if (!Number.isInteger(value) || value < 0) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be a whole number of zero ` +
        `or more, got ${value}.`,
    )
  }
  return value
}

/** Read an amount, and refuse anything that is not a string with two decimals. */
export function readMoney(source: Record<string, unknown>, key: string, requestPath: string): Money {
  const value = readText(source, key, requestPath)
  if (!MONEY_PATTERN.test(value)) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be money written as a ` +
        `string with two decimals, for example "280.00", got "${value}".`,
    )
  }
  return value
}

/** Read a field that must be an array, reading every item with `readItem`. */
export function readList<Item>(
  source: Record<string, unknown>,
  key: string,
  requestPath: string,
  readItem: (value: unknown, requestPath: string) => Item,
): Item[] {
  const value = source[key]
  if (!Array.isArray(value)) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be a list, got ` +
        `${value === undefined ? 'nothing' : typeof value}.`,
    )
  }
  return value.map((item: unknown) => readItem(item, requestPath))
}
