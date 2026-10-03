/**
 * Dates for a spec that books, searches or reads the diary, counted from today
 * at the branches, and the time of day there.
 *
 * The branches trade in Cape Town, so "today" for a hire means today there and
 * not in whatever zone the machine running the tests is set to.
 */

/** The time zone the branches trade in. */
const BRANCH_TIME_ZONE = 'Africa/Johannesburg'

/** A date some days from today in branch time, as `YYYY-MM-DD`. */
export function dateFromToday(days: number): string {
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

/** The time of day at the branches now, as `HH:MM` on a 24 hour clock, the
 *  way the API writes the hours a branch opens and closes. */
export function clockTimeAtTheBranches(): string {
  const parts = new Map(
    new Intl.DateTimeFormat('en-ZA', {
      timeZone: BRANCH_TIME_ZONE,
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  )
  return `${parts.get('hour')}:${parts.get('minute')}`
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
