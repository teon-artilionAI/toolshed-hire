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
import type { IsoDate, IsoTimestamp, Money } from './contract'

/** Money on the wire. Digits, a point, and exactly two decimals. */
const MONEY_PATTERN = /^\d+\.\d{2}$/

/** A percentage on the wire. Digits, a point, and exactly two decimals. */
const PERCENT_PATTERN = /^\d+\.\d{2}$/

/** The shape of a calendar date on the wire. */
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

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

/** Read a percentage, and refuse anything that is not a string with two
 *  decimals. The API writes a rate the way it writes money, so "15.00". */
export function readPercent(source: Record<string, unknown>, key: string, requestPath: string): string {
  const value = readText(source, key, requestPath)
  if (!PERCENT_PATTERN.test(value)) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be a percentage written as ` +
        `a string with two decimals, for example "15.00", got "${value}".`,
    )
  }
  return value
}

/** Read a calendar date, and refuse anything that is not written `YYYY-MM-DD`
 *  or cannot be read as a date. A screen formats what this returns, and a date
 *  it cannot format would take the whole screen down. */
export function readDate(source: Record<string, unknown>, key: string, requestPath: string): IsoDate {
  const value = readText(source, key, requestPath)
  if (!DATE_PATTERN.test(value) || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be a date written as ` +
        `YYYY-MM-DD, got "${value}".`,
    )
  }
  return value
}

/** Read an instant the contract allows to be null, and refuse a string that
 *  is not one. A missing field is not null. */
export function readNullableTimestamp(
  source: Record<string, unknown>,
  key: string,
  requestPath: string,
): IsoTimestamp | null {
  if (source[key] === null) return null
  const value = readText(source, key, requestPath)
  if (Number.isNaN(Date.parse(value))) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be an ISO 8601 instant, ` +
        `got "${value}".`,
    )
  }
  return value
}

/** Read a field that must be one of a fixed set of words. */
export function readOneOf<Word extends string>(
  source: Record<string, unknown>,
  key: string,
  requestPath: string,
  words: readonly Word[],
): Word {
  const value = readText(source, key, requestPath)
  const word = words.find((known) => known === value)
  if (word === undefined) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} in the response from ${requestPath} to be one of ` +
        `${words.join(', ')}, got "${value}".`,
    )
  }
  return word
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
