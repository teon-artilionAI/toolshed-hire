/**
 * Calendar arithmetic for the diary on SC-11.
 *
 * The diary moves a day or a week at a time and names each day it shows. The
 * API speaks in `YYYY-MM-DD` dates, so that is what goes in and comes out.
 * Every sum is done on the calendar in UTC, where a day is always 24 hours
 * long, so the change of a clock somewhere can never move a date. A day is
 * named in UTC for the same reason. These dates have no time of day, and
 * naming them in the zone of the device could name the day before.
 *
 * A trade counter's week starts on a Monday, so that is where a week starts.
 */

/** How many days a week of the diary shows. */
export const DAYS_IN_WEEK = 7

const MS_PER_DAY = 86_400_000

/** What a calendar date looks like on the wire. */
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** `getUTCDay` counts from Sunday. The diary counts from Monday. */
const DAYS_FROM_SUNDAY_TO_MONDAY = 6

const DAY_NAME = new Intl.DateTimeFormat('en-ZA', {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
})

/** Midnight at the start of a date, in UTC. */
function utcMidnight(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`)
}

/**
 * Read a date from the address, which anybody can write.
 *
 * @returns The date, or null when it is missing, not written `YYYY-MM-DD`, or
 *   not a day on the calendar, such as the 31st of September.
 */
export function readIsoDate(value: string | null): string | null {
  if (value === null || !ISO_DATE_PATTERN.test(value)) return null
  const day = utcMidnight(value)
  if (Number.isNaN(day.getTime()) || day.toISOString().slice(0, 10) !== value) return null
  return value
}

/** The date a number of days after another. A negative number goes back. */
export function addDays(iso: string, days: number): string {
  return new Date(utcMidnight(iso).getTime() + days * MS_PER_DAY).toISOString().slice(0, 10)
}

/** The Monday of the week a date falls in. */
export function startOfWeek(iso: string): string {
  const daysSinceMonday = (utcMidnight(iso).getUTCDay() + DAYS_FROM_SUNDAY_TO_MONDAY) % DAYS_IN_WEEK
  return addDays(iso, -daysSinceMonday)
}

/** A date written out in full, for example "Saturday 3 October 2026". */
export function dayName(iso: string): string {
  const parts = new Map(DAY_NAME.formatToParts(utcMidnight(iso)).map((part) => [part.type, part.value]))
  return `${parts.get('weekday')} ${parts.get('day')} ${parts.get('month')} ${parts.get('year')}`
}
