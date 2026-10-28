/**
 * Readers for the trading calendar members the API sends: a branch's weekly
 * hours and closed days, and whether the counter trades on one day.
 *
 * The catalogue reads the first two with each branch, and the counter reads
 * the third with its dashboard and each day of its diary, so they live here
 * once rather than in both.
 */

import type { ClosedDay, ClosedDayKind, OpeningHours, TradingDay } from './contract'
import { readCount, readDate, readFlag, readNullableOneOf, readNullableText, readObject, readOneOf, readText } from './read'

/** The reasons a branch can be closed on a day, as the API names them. */
export const CLOSED_DAY_KINDS: readonly ClosedDayKind[] = ['weekly', 'public_holiday', 'closure']

export function readOpeningHours(value: unknown, path: string): OpeningHours {
  const record = readObject(value, path, "a branch's hours on one weekday")
  return {
    weekday: readCount(record, 'weekday', path),
    opensAt: readText(record, 'opensAt', path),
    closesAt: readText(record, 'closesAt', path),
  }
}

export function readClosedDay(value: unknown, path: string): ClosedDay {
  const record = readObject(value, path, 'a closed day')
  return {
    day: readDate(record, 'day', path),
    reason: readText(record, 'reason', path),
    kind: readOneOf(record, 'kind', path, CLOSED_DAY_KINDS),
  }
}

export function readTradingDay(value: unknown, path: string): TradingDay {
  const record = readObject(value, path, 'whether the branch trades on a day')
  return {
    open: readFlag(record, 'open', path),
    opensAt: readNullableText(record, 'opensAt', path),
    closesAt: readNullableText(record, 'closesAt', path),
    closedReason: readNullableText(record, 'closedReason', path),
    closedKind: readNullableOneOf(record, 'closedKind', path, CLOSED_DAY_KINDS),
  }
}
