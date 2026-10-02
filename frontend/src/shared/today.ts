/**
 * Today's date, as the branches see it.
 *
 * All three branches trade in Cape Town, so "today" means today in South
 * African time and not in whatever zone the visitor's device is set to. A
 * customer booking from London at eleven at night must not be offered a
 * collection date the branch already considers yesterday.
 *
 * The API speaks in `YYYY-MM-DD` dates, so that is what this returns.
 */

/** The time zone the three branches trade in. */
export const BRANCH_TIME_ZONE = 'Africa/Johannesburg'

const BRANCH_DATE_PARTS = new Intl.DateTimeFormat('en-ZA', {
  timeZone: BRANCH_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

/**
 * The calendar date in `Africa/Johannesburg` at a given instant.
 *
 * @param now The instant to read. It defaults to the present, and a test passes
 *   its own so the answer does not depend on when the test runs.
 * @returns The date as `YYYY-MM-DD`.
 * @throws RangeError when `now` is not a valid date.
 */
export function todayInBranchTime(now: Date = new Date()): string {
  if (Number.isNaN(now.getTime())) {
    throw new RangeError('todayInBranchTime was given an invalid Date, so there is no day to read.')
  }
  // I assemble the date from its parts and do not trust the order a locale
  // prints them in, which differs between runtimes.
  const parts = new Map(BRANCH_DATE_PARTS.formatToParts(now).map((part) => [part.type, part.value]))
  return `${parts.get('year')}-${parts.get('month')}-${parts.get('day')}`
}
