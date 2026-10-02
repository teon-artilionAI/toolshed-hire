/**
 * The hire period. Dates, days and whether the pair makes sense.
 *
 * Kept apart from anything about stock because these are calendar questions,
 * and every customer screen asks them before it asks anything about tools.
 *
 * A period is half open, `[start, end)`, matching the schema and the API. A
 * hire from the 6th to the 10th occupies the 6th, 7th, 8th and 9th, and the
 * unit is free again on the 10th. That is what "you are charged to the morning
 * you bring it back" means at the counter.
 *
 * Nothing here knows what day it is. Every function that needs today is given
 * it, so a screen passes the real date in branch time and a test passes its
 * own.
 */

import { daysBetween, formatDate } from '../../shared/format'

/** Longest hire the branches will take online. Anything longer is a phone
 *  call, which is how they actually work. */
export const MAX_HIRE_DAYS = 28

/** The hire a screen opens with before the customer has chosen dates. */
export const DEFAULT_HIRE_DAYS = 4

/** Guards the day loop against a nonsense period typed into a date field. */
const MAX_LOOP_DAYS = 400

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/**
 * Whether a string is a real calendar date written as `YYYY-MM-DD`.
 *
 * An address bar is user input, so a date read from it is checked with this
 * before anything tries to format it. The 31st of February has the right shape
 * and is still refused.
 */
export function isIsoDate(value: string): boolean {
  if (!ISO_DATE_PATTERN.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value
}

/** ISO dates only, so string comparison is date comparison and no local
 *  timezone can shift a day. */
export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** Every day in the half open period [start, end). */
export function eachDay(startIso: string, endIso: string): string[] {
  const days: string[] = []
  let cursor = startIso
  while (cursor < endIso && days.length < MAX_LOOP_DAYS) {
    days.push(cursor)
    cursor = addDays(cursor, 1)
  }
  return days.length > 0 ? days : [startIso]
}

export interface HirePeriod {
  startIso: string
  endIso: string
}

/** The period a screen opens with. Collect today, bring it back in four days. */
export function defaultPeriod(today: string): HirePeriod {
  return { startIso: today, endIso: addDays(today, DEFAULT_HIRE_DAYS) }
}

/**
 * Chargeable days in a hire period, matching the half open rule in the
 * schema. The 6th to the 10th is four days, and never fewer than one, so a
 * mistyped period cannot produce a free hire.
 */
export function hireDays(startIso: string, endIso: string): number {
  return Math.max(1, daysBetween(startIso, endIso))
}

/**
 * The period in words, for example "6 Mar 2026 to 10 Mar 2026".
 *
 * @returns Null when either date is not a real date, so a caller can fall back
 *   to other wording and nothing tries to format a date that does not exist.
 */
export function describePeriod(startIso: string, endIso: string): string | null {
  if (!isIsoDate(startIso) || !isIsoDate(endIso)) return null
  return `${formatDate(startIso)} to ${formatDate(endIso)}`
}

/**
 * Validates a hire period. Returns a sentence saying what is wrong and how
 * to put it right, or null when the period is usable. The wording is the
 * customer's, not the schema's.
 *
 * @param today The earliest day a hire may start, as `YYYY-MM-DD`.
 */
export function validatePeriod(startIso: string, endIso: string, today: string): string | null {
  if (!isIsoDate(startIso)) return 'Choose a collection date.'
  if (!isIsoDate(endIso)) return 'Choose a return date.'
  if (startIso < today) {
    return `Collection cannot be in the past. Choose ${formatDate(today)} or later.`
  }
  if (endIso <= startIso) {
    return 'The return date must be after the collection date. A one day hire comes back the next morning.'
  }
  if (eachDay(startIso, endIso).length > MAX_HIRE_DAYS) {
    return `Online hires run up to ${MAX_HIRE_DAYS} days. For a longer job, ring your branch and we will arrange it.`
  }
  return null
}
