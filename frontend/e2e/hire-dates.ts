/**
 * Dates for a spec that books, searches or reads the diary, counted from today
 * at the branches.
 *
 * The branches trade in Cape Town, so "today" for a hire means today there and
 * not in whatever zone the machine running the tests is set to.
 */

/** The time zone the branches trade in. */
const BRANCH_TIME_ZONE = 'Africa/Johannesburg'

/** A test-only date, when the run moves the API and browser clock. */
const TEST_BUSINESS_DATE = /^\d{4}-\d{2}-\d{2}$/

/** A date some days from today in branch time, as `YYYY-MM-DD`. */
export function dateFromToday(days: number): string {
  const fixed = process.env.TEST_BUSINESS_DATE
  if (fixed !== undefined) {
    if (!TEST_BUSINESS_DATE.test(fixed)) {
      throw new Error(`TEST_BUSINESS_DATE is "${fixed}", not a date such as 2026-12-16.`)
    }
    const date = new Date(`${fixed}T00:00:00Z`)
    date.setUTCDate(date.getUTCDate() + days)
    return date.toISOString().slice(0, 10)
  }
  const parts = new Map(
    new Intl.DateTimeFormat('en-ZA', {
      timeZone: BRANCH_TIME_ZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  )
  const date = new Date(`${parts.get('year')}-${parts.get('month')}-${parts.get('day')}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** `getUTCDay` counts from Sunday, and a trade counter's week from Monday. */
const DAYS_FROM_SUNDAY_TO_MONDAY = 6
const DAYS_IN_WEEK = 7

/** The Monday of the week a `YYYY-MM-DD` date falls in. */
export function mondayOf(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + DAYS_FROM_SUNDAY_TO_MONDAY) % DAYS_IN_WEEK))
  return date.toISOString().slice(0, 10)
}

/** A `YYYY-MM-DD` date written out the way the diary names a day, for
 *  example "Saturday 3 October 2026". */
export function dayInWords(iso: string): string {
  const parts = new Map(
    new Intl.DateTimeFormat('en-ZA', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
      .formatToParts(new Date(`${iso}T00:00:00Z`))
      .map((part) => [part.type, part.value]),
  )
  return `${parts.get('weekday')} ${parts.get('day')} ${parts.get('month')} ${parts.get('year')}`
}

/*
 * The days the branches trade, as a journey needs them to pick dates the API
 * will accept. The seed gives every branch the design's week, closed on a
 * Sunday, and no branch a closure day, so a day is a trading day unless it is
 * a Sunday or a public holiday. The holidays follow the Public Holidays Act
 * exactly as backend/app/domain/public_holidays.py works them out, which the
 * backend's own tests check against the government's list. If the two ever
 * disagreed, a journey would be refused with a sentence naming the date.
 */

/** The holidays the Act fixes by date, as month and day. */
const FIXED_HOLIDAYS: readonly (readonly [number, number])[] = [
  [1, 1], [3, 21], [4, 27], [5, 1], [6, 16], [8, 9], [9, 24], [12, 16], [12, 25], [12, 26],
]
const SUNDAY = 0
/** How far a search for an open day looks. No run of closed days is longer. */
const LONGEST_CLOSURE_DAYS = 10

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function isoOf(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** Easter Sunday, by the anonymous Gregorian algorithm. */
function easterSunday(year: number): string {
  const a = year % 19
  const b = Math.floor(year / 100)
  const c = year % 100
  const d = Math.floor(b / 4)
  const e = b % 4
  const f = Math.floor((b + 8) / 25)
  const g = Math.floor((b - f + 1) / 3)
  const h = (19 * a + b - d - g + 15) % 30
  const i = Math.floor(c / 4)
  const k = c % 4
  const l = (32 + 2 * e + 2 * i - h - k) % 7
  const m = Math.floor((a + 11 * h + 22 * l) / 451)
  const month = Math.floor((h + l - 7 * m + 114) / 31)
  const day = ((h + l - 7 * m + 114) % 31) + 1
  return isoOf(year, month, day)
}

function publicHolidays(year: number): Set<string> {
  const easter = easterSunday(year)
  const named = [...FIXED_HOLIDAYS.map(([month, day]) => isoOf(year, month, day)), addDays(easter, -2), addDays(easter, 1)]
  const holidays = new Set(named)
  for (const day of named) {
    if (new Date(`${day}T00:00:00Z`).getUTCDay() === SUNDAY && !holidays.has(addDays(day, 1))) {
      holidays.add(addDays(day, 1))
    }
  }
  return holidays
}

/** Whether the seeded branches trade on a `YYYY-MM-DD` day. */
export function isTradingDay(iso: string): boolean {
  if (new Date(`${iso}T00:00:00Z`).getUTCDay() === SUNDAY) return false
  return !publicHolidays(Number(iso.slice(0, 4))).has(iso)
}

/** The first trading day on or after a `YYYY-MM-DD` day. */
export function openDayFrom(iso: string): string {
  let day = iso
  for (let step = 0; step < LONGEST_CLOSURE_DAYS && !isTradingDay(day); step += 1) day = addDays(day, 1)
  return day
}

/** The first trading day on or after a number of days from today. */
export function openDayFromToday(days: number): string {
  return openDayFrom(dateFromToday(days))
}

/**
 * A hire that starts on the first trading day `collectInDays` from today and
 * comes back on the first trading day at least `hireDays` after that.
 */
export function openHireFromToday(collectInDays: number, hireDays: number): { from: string; to: string } {
  const from = openDayFromToday(collectInDays)
  return { from, to: openDayFrom(addDays(from, hireDays)) }
}

/** Whether the branches trade today, so a hire can go out and come back today. */
export function todayIsTradingDay(): boolean {
  return isTradingDay(dateFromToday(0))
}

/** Why a journey that hands equipment over today is skipped on a closed day. */
export const CLOSED_TODAY_REASON =
  'The branches do not trade today, so nothing can be handed over or taken back today. ' +
  'This journey runs on every trading day.'
