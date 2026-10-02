/** Formatting helpers. Money and dates appear on nearly every screen, so
 *  they are formatted in one place rather than inline at each call site.
 *
 *  The fixture `TODAY` below is the default "as at" date for the overdue
 *  helpers, which only the screens still on fixtures use. A screen that reads
 *  from the API takes today from today.ts. */

import { TODAY } from './fixtures'

const RAND = new Intl.NumberFormat('en-ZA', {
  style: 'currency',
  currency: 'ZAR',
  minimumFractionDigits: 2,
})

/** Money as the API writes it. An optional minus, digits, and up to two
 *  decimals. The API always sends two, and I accept fewer so a figure typed in
 *  by hand, such as "280", still reads. */
const WIRE_MONEY = /^(-?)(\d+)(?:\.(\d{1,2}))?$/

const CENT_DIGITS = 2

interface ExactMoney {
  negative: boolean
  whole: bigint
  /** Always two digits. */
  cents: string
}

/**
 * Split a money string into its sign, its rand and its cents, exactly.
 *
 * @throws RangeError when the string is not money as the API writes it. A
 *   figure I cannot read exactly is never shown as a guess.
 */
function parseWireMoney(amount: string): ExactMoney {
  const match = WIRE_MONEY.exec(amount.trim())
  if (!match) {
    throw new RangeError(
      `Cannot read "${amount}" as money. Expected digits with up to two decimals, for example "280.00".`,
    )
  }
  return {
    negative: match[1] === '-',
    whole: BigInt(match[2]),
    cents: (match[3] ?? '').padEnd(CENT_DIGITS, '0'),
  }
}

/** A locale formatter writes its spaces as no-break spaces. I turn them into
 *  plain ones, so a figure can be matched and copied as ordinary text. */
function tidy(formatted: string): string {
  return formatted.replace('ZAR', 'R').replace(/\s/g, ' ')
}

/**
 * Format rand. Always two decimals, so columns of figures line up.
 *
 * @param amount A number, or a string as the API sends it, such as "280.00".
 *   A string never passes through a float. The rand are grouped as a whole
 *   number and the cents are written as they arrived, so the figure shown is
 *   the figure sent however large it is.
 * @throws RangeError when a string is not money as the API writes it.
 */
export function money(amount: number | string): string {
  if (typeof amount === 'number') return tidy(RAND.format(amount))
  const { negative, whole, cents } = parseWireMoney(amount)
  const isZero = whole === 0n && Number(cents) === 0
  const written = RAND.formatToParts(whole)
    .map((part) => (part.type === 'fraction' ? cents : part.value))
    .join('')
  return tidy(negative && !isZero ? `-${written}` : written)
}

/**
 * Whether a money string is nothing at all, for example "0.00".
 *
 * A screen uses it to leave out a line that would only say zero, such as a
 * discount nobody was given.
 *
 * @throws RangeError when the string is not money as the API writes it.
 */
export function isNoMoney(amount: string): boolean {
  const { whole, cents } = parseWireMoney(amount)
  return whole === 0n && Number(cents) === 0
}

/** A percentage as the API writes it. Digits with up to two decimals. */
const WIRE_PERCENT = /^\d+(?:\.\d{1,2})?$/

const PERCENT = new Intl.NumberFormat('en-ZA', { maximumFractionDigits: 2 })

/**
 * Format a percentage the API sent, so "15.00" reads as "15%".
 *
 * Decimals that are all zeros are dropped and any others are kept, so "12.50"
 * reads as twelve and a half percent.
 *
 * @param rate A percentage as the API sends it, such as "15.00".
 * @throws RangeError when the string is not a percentage as the API writes it.
 */
export function percent(rate: string): string {
  if (!WIRE_PERCENT.test(rate.trim())) {
    throw new RangeError(
      `Cannot read "${rate}" as a percentage. Expected digits with up to two decimals, for example "15.00".`,
    )
  }
  return `${PERCENT.format(Number(rate))}%`
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
