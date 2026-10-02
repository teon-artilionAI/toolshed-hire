/**
 * Dates for a spec that books or searches, counted from today at the branches.
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
