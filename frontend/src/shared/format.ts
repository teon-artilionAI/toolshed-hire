/** Formatting helpers. Money and dates appear on nearly every screen, so
 *  they are formatted in one place rather than inline at each call site. */

import { TODAY } from './fixtures'

const RAND = new Intl.NumberFormat('en-ZA', {
  style: 'currency',
  currency: 'ZAR',
  minimumFractionDigits: 2,
})

/** Format rand. Always two decimals, so columns of figures line up. */
export function money(amount: number): string {
  return RAND.format(amount).replace('ZAR', 'R').replace(/\s/g, ' ')
}

const DATE_LONG = new Intl.DateTimeFormat('en-ZA', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

const DATE_SHORT = new Intl.DateTimeFormat('en-ZA', {
  day: 'numeric',
  month: 'short',
})

export function formatDate(iso: string): string {
  return DATE_LONG.format(new Date(iso))
}

export function formatDateShort(iso: string): string {
  return DATE_SHORT.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return `${DATE_SHORT.format(d)} ${d.toTimeString().slice(0, 5)}`
}

/**
 * Whole days between two ISO dates, treating the period as half open.
 *
 * A hire from the 6th to the 10th is four days, and the unit is free again
 * on the 10th. This mirrors the `[start, end)` semantics the schema uses,
 * so the prototype and the documented rules agree.
 */
export function daysBetween(startIso: string, endIso: string): number {
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime()
  return Math.max(0, Math.round(ms / 86_400_000))
}

/** Days a rental is past its due date, relative to the fixture "today". */
export function daysOverdue(dueBackOn: string, asAt: string = TODAY): number {
  return daysBetween(dueBackOn, asAt)
}

export function isOverdue(dueBackOn: string, asAt: string = TODAY): boolean {
  return new Date(asAt) > new Date(dueBackOn)
}

/** Title case a SCREAMING_SNAKE enum for display. */
export function humanise(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
