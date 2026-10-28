/**
 * The days the branches trade, as the screens need them before they ask the
 * server anything.
 *
 * Each branch arrives from `GET /api/branches` with every day it is closed from
 * today to the last day a hire booked today could end. A date field uses that
 * to open on days a hire can actually start and end, and to say at once when
 * a customer picks a closed day, so they are not sent to the server to be
 * told. The server checks the same days again and has the last word.
 *
 * A customer who has not chosen a branch may collect from any of them, so a
 * day counts as closed for them only when every branch is closed on it. A
 * counter assistant books for one branch, so for them a day is closed when
 * that branch is.
 */

import type { Branch, ClosedDay, IsoDate } from './api/contract'
import { formatDate } from './format'

/** The closed days that matter to one question, by date. */
export type ClosedDays = ReadonlyMap<IsoDate, ClosedDay>

const NO_CLOSED_DAYS: ClosedDays = new Map()

/** How far the search for an open day looks before it gives up. The horizon a
 *  branch's closed days cover is 118 days, so nothing closes for longer. */
const LONGEST_SEARCH_DAYS = 120

function addDays(iso: IsoDate, days: number): IsoDate {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** Every day one branch is closed, by date. */
export function closedDaysAt(branch: Branch | undefined): ClosedDays {
  if (branch === undefined) return NO_CLOSED_DAYS
  return new Map(branch.closedDays.map((closed) => [closed.day, closed]))
}

/**
 * The days every branch is closed, by date, with the first branch's reason.
 * A day only one branch is closed on is left out, because another may serve.
 */
export function closedEverywhere(branches: readonly Branch[] | undefined): ClosedDays {
  if (branches === undefined || branches.length === 0) return NO_CLOSED_DAYS
  const [first, ...rest] = branches.map(closedDaysAt)
  const shared = new Map<IsoDate, ClosedDay>()
  for (const [day, closed] of first) {
    if (rest.every((other) => other.has(day))) shared.set(day, closed)
  }
  return shared
}

/** The first day on or after `from` that is not closed. */
export function nextOpenDay(from: IsoDate, closed: ClosedDays): IsoDate {
  let day = from
  for (let step = 0; step < LONGEST_SEARCH_DAYS && closed.has(day); step += 1) {
    day = addDays(day, 1)
  }
  return day
}

/**
 * A period of about `days` days that starts and ends on open days. The start
 * moves forward to the first open day, and the end to the first open day at
 * least `days` after the start.
 */
export function openPeriod(
  startIso: IsoDate,
  days: number,
  closed: ClosedDays,
): { startIso: IsoDate; endIso: IsoDate } {
  const start = nextOpenDay(startIso, closed)
  return { startIso: start, endIso: nextOpenDay(addDays(start, days), closed) }
}

/**
 * The sentence for a day a hire cannot start or end on, or null when it can.
 *
 * @param collecting True for the first day of the hire, false for the return.
 */
export function closedDayProblem(day: IsoDate, closed: ClosedDays, collecting: boolean): string | null {
  const found = closed.get(day)
  if (found === undefined) return null
  const action = collecting ? 'collect' : 'bring equipment back'
  const when = formatDate(day)
  const reason = found.kind === 'weekly' ? `The branch ${found.reason}` : `The branch is closed for ${found.reason}`
  return `${reason}, so you cannot ${action} on ${when}. The next open day is ${formatDate(nextOpenDay(day, closed))}.`
}
