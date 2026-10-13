/**
 * The words and the small rules of the owner's trading calendar.
 *
 * The closed days are grouped by the month they fall in, so a year of them
 * reads as twelve short lists. Each day is named in full and in UTC, because
 * these dates have no time of day. A branch is named by the name the API gives
 * it, and a day with no branch closes every branch.
 *
 * The form checks what it can before it asks the server, so an owner hears
 * about an empty reason or a day that has passed at once. The rules are the
 * server's all the same, and it has the last word on each of them.
 */

import { CLOSURE_REASON_MAX_LENGTH, FURTHEST_CLOSURE_DAYS } from '../../shared/api/closure-days'
import type { CalendarClosedDay, ClosureImpact, IsoDate, StrandedBooking } from '../../shared/api/contract'
import { countOf } from '../counter/counter-labels'
import { addDays, dayName, readIsoDate } from '../counter/diary-dates'
import { EVERY_BRANCH, branchWords } from './staff-words'

/** A branch by its name, or every branch, said the way SC-23 says it. */
export { EVERY_BRANCH, branchWords }

/** The value the branch menu gives every branch. A branch code is never this. */
export const EVERY_BRANCH_VALUE = '*'

/** The month part of a date, `YYYY-MM`. */
const MONTH_LENGTH = 7

const MONTH_NAME = new Intl.DateTimeFormat('en-ZA', { month: 'long', year: 'numeric', timeZone: 'UTC' })

/** What each kind of closed day is called on the list. */
export const KIND_LABEL: Record<CalendarClosedDay['kind'], string> = {
  public_holiday: 'Public holiday',
  closure: 'Closure day',
}

/** What a booking does on the day, by the day of the hire it falls on. */
export const HIRE_DAY_WORDS: Record<StrandedBooking['hireDay'], string> = {
  collection: 'Collects on that day',
  return: 'Brings the equipment back on that day',
}

/** The closed days of one month, in the order the server sent them. */
export interface MonthOfClosedDays {
  /** `YYYY-MM`, which keys the month. */
  key: string
  /** The month in words, for example "March 2026". */
  label: string
  days: CalendarClosedDay[]
}

/** Group the closed days by the month they fall in, keeping their order. */
export function monthsOf(days: readonly CalendarClosedDay[]): MonthOfClosedDays[] {
  const months: MonthOfClosedDays[] = []
  for (const day of days) {
    const key = day.day.slice(0, MONTH_LENGTH)
    const last = months.at(-1)
    if (last !== undefined && last.key === key) {
      last.days.push(day)
    } else {
      months.push({ key, label: MONTH_NAME.format(new Date(`${key}-01T00:00:00Z`)), days: [day] })
    }
  }
  return months
}

/** A day written out in full, for example "Friday 20 March 2026". */
export function dayWords(day: IsoDate): string {
  return dayName(day)
}

/** The last day the owner can close, counted from today. */
export function lastDayToClose(today: IsoDate): IsoDate {
  return addDays(today, FURTHEST_CLOSURE_DAYS)
}

/** What the owner has typed into the form, as the form holds it. */
export interface ClosureDraft {
  /** A branch code, `EVERY_BRANCH_VALUE` for every branch, or empty for none chosen. */
  branch: string
  day: string
  reason: string
}

/** A sentence for each field the form refuses before it asks the server. */
export type DraftProblems = Partial<Record<keyof ClosureDraft, string>>

/**
 * Check the draft against the rules the form can know, in the order of the
 * fields.
 *
 * @param today The day at the branches, which a test passes in.
 */
export function draftProblems(draft: ClosureDraft, today: IsoDate): DraftProblems {
  const problems: DraftProblems = {}
  if (draft.branch === '') problems.branch = 'Choose a branch, or every branch.'
  const day = readIsoDate(draft.day)
  if (day === null) {
    problems.day = 'Choose the day to close.'
  } else if (day < today) {
    problems.day = 'Choose today or a later day. A day that has passed cannot be closed.'
  } else if (day > lastDayToClose(today)) {
    problems.day = `Choose a day at most ${FURTHEST_CLOSURE_DAYS} days from today.`
  }
  const reason = draft.reason.trim()
  if (reason === '') {
    problems.reason = 'Write the reason. Customers read it when they choose a date.'
  } else if (reason.length > CLOSURE_REASON_MAX_LENGTH) {
    problems.reason = `Keep the reason to ${CLOSURE_REASON_MAX_LENGTH} characters.`
  }
  return problems
}

/** The branch code the API is sent for the draft's branch, null for every branch. */
export function branchCodeOf(draft: ClosureDraft): string | null {
  return draft.branch === EVERY_BRANCH_VALUE ? null : draft.branch
}

/** How many characters of the reason are left, said under the box. */
export function reasonCounter(reason: string): string {
  const left = CLOSURE_REASON_MAX_LENGTH - reason.trim().length
  return left >= 0
    ? `${countOf(left, 'character', 'characters')} left of ${CLOSURE_REASON_MAX_LENGTH}.`
    : `${countOf(-left, 'character', 'characters')} too many.`
}

/** The line above the bookings a closure would strand. */
export function impactLine(impact: ClosureImpact): string {
  if (impact.total === 0) return 'No booking starts or ends on that day.'
  const count = countOf(impact.total, 'booking starts or ends', 'bookings start or end')
  const shown = impact.items.length < impact.total ? ` The first ${impact.items.length} are listed.` : ''
  return `${count} on that day.${shown}`
}
