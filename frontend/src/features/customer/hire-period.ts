/**
 * The hire period: dates, days and whether the pair makes sense.
 *
 * Kept apart from the availability engine because these are calendar
 * questions, not stock questions, and every customer screen asks them
 * before it asks anything about tools.
 *
 * A period is half open, `[start, end)`, matching the schema. A hire from
 * the 6th to the 10th occupies the 6th, 7th, 8th and 9th, and the unit is
 * free again on the 10th. That is what "you are charged to the morning you
 * bring it back" means at the counter.
 */

import { TODAY } from '../../shared/fixtures'
import { formatDate } from '../../shared/format'

/** Longest hire the branches will take online. Anything longer is a phone
 *  call, which is how they actually work. */
export const MAX_HIRE_DAYS = 28

/** How far ahead the day by day strip on SC-03 looks. */
export const AVAILABILITY_HORIZON_DAYS = 14

/** Guards the day loop against a nonsense period typed into a date field. */
const MAX_LOOP_DAYS = 400

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

export const DEFAULT_START = TODAY
export const DEFAULT_END = addDays(TODAY, 4)

/**
 * Validates a hire period. Returns a sentence saying what is wrong and how
 * to put it right, or null when the period is usable. The wording is the
 * customer's, not the schema's.
 */
export function validatePeriod(startIso: string, endIso: string): string | null {
  if (!startIso) return 'Choose a collection date.'
  if (!endIso) return 'Choose a return date.'
  if (startIso < TODAY) {
    return `Collection cannot be in the past. Choose ${formatDate(TODAY)} or later.`
  }
  if (endIso <= startIso) {
    return 'The return date must be after the collection date. A one day hire comes back the next morning.'
  }
  if (eachDay(startIso, endIso).length > MAX_HIRE_DAYS) {
    return `Online hires run up to ${MAX_HIRE_DAYS} days. For a longer job, ring your branch and we will arrange it.`
  }
  return null
}
