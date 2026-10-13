/**
 * The owner's trading calendar. The days a branch is closed beyond its week,
 * the bookings a new closure would strand, and adding and cancelling a
 * closure day.
 *
 * Every route is for an administrator, and the API refuses anyone else with a
 * 403. A closure day closes one branch, or every branch, on one day, with a
 * reason customers read. Closing a day never touches a booking. The owner reads
 * the bookings that start or end on it and the hires due back on it first, and
 * rings each customer, which is
 * why the impact is a read of its own.
 *
 * The writes are sent once for each press of a button and never repeated by
 * the client, because a request that timed out may still have reached the
 * server and closed the day. A closure is never deleted. Cancelling one opens
 * the day again and keeps the row.
 */

import { api } from './client'
import type {
  CalendarClosedDay,
  CalendarClosedDays,
  CalendarQuery,
  ClosureDay,
  ClosureImpact,
  ClosureImpactQuery,
  NewClosureRequest,
  StrandedBooking,
} from './contract'
import {
  readCount,
  readDate,
  readList,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readText,
  readTimestamp,
} from './read'

const CLOSURE_DAYS_ENDPOINT = '/admin/closure-days'
const IMPACT_ENDPOINT = `${CLOSURE_DAYS_ENDPOINT}/impact`

/** The two reasons the owner's list shows, as the API names them. */
export const CALENDAR_KINDS: readonly CalendarClosedDay['kind'][] = ['public_holiday', 'closure']

/** The two days of a hire a closure can fall on, as the API names them. */
export const HIRE_DAYS: readonly StrandedBooking['hireDay'][] = ['collection', 'return', 'due_back']

/** The longest reason the API keeps for a closure, in characters. */
export const CLOSURE_REASON_MAX_LENGTH = 120

/** How far ahead a day can be closed, in days from today. */
export const FURTHEST_CLOSURE_DAYS = 366

function readCalendarClosedDay(value: unknown, path: string): CalendarClosedDay {
  const record = readObject(value, path, 'a closed day')
  return {
    day: readDate(record, 'day', path),
    branchCode: readNullableText(record, 'branchCode', path),
    reason: readText(record, 'reason', path),
    kind: readOneOf(record, 'kind', path, CALENDAR_KINDS),
    closureId: readNullableText(record, 'closureId', path),
  }
}

function readCalendar(value: unknown, path: string): CalendarClosedDays {
  const record = readObject(value, path, 'the closed days')
  return { items: readList(record, 'items', path, readCalendarClosedDay) }
}

/** Read one closure day, as a new closure or a cancellation answers with it. */
export function readClosureDay(value: unknown, path: string): ClosureDay {
  const record = readObject(value, path, 'a closure day')
  return {
    id: readText(record, 'id', path),
    branchCode: readNullableText(record, 'branchCode', path),
    day: readDate(record, 'day', path),
    reason: readText(record, 'reason', path),
    createdAt: readTimestamp(record, 'createdAt', path),
    cancelledAt: readNullableTimestamp(record, 'cancelledAt', path),
  }
}

function readStrandedBooking(value: unknown, path: string): StrandedBooking {
  const record = readObject(value, path, 'a booking on the day')
  return {
    reference: readText(record, 'reference', path),
    branchCode: readText(record, 'branchCode', path),
    customerName: readText(record, 'customerName', path),
    customerPhone: readText(record, 'customerPhone', path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    hireDay: readOneOf(record, 'hireDay', path, HIRE_DAYS),
  }
}

function readImpact(value: unknown, path: string): ClosureImpact {
  const record = readObject(value, path, 'the bookings on the day')
  return {
    items: readList(record, 'items', path, readStrandedBooking),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/admin/closure-days. Every public holiday and live closure day in
 * the span, by day. A span left out runs from today for a year.
 *
 * @throws ApiError with status 422 naming `to`, and 403 for anyone but an
 *   administrator.
 */
export function listCalendar(query: CalendarQuery, signal?: AbortSignal): Promise<CalendarClosedDays> {
  return api.get(CLOSURE_DAYS_ENDPOINT, readCalendar, { query, signal })
}

/**
 * GET /api/admin/closure-days/impact. The held and confirmed bookings that
 * start or end on the day at the branch, or at any branch, and the hires still
 * out whose equipment is due back that day.
 *
 * @throws ApiError with status 422 naming `branchCode` or `day`, and 403 for
 *   anyone but an administrator.
 */
export function readClosureImpact(query: ClosureImpactQuery, signal?: AbortSignal): Promise<ClosureImpact> {
  return api.get(IMPACT_ENDPOINT, readImpact, { query, signal })
}

/**
 * POST /api/admin/closure-days. Closes the branch, or every branch, on the day
 * and answers 201 with the closure.
 *
 * @throws ApiError with status 422 naming `branchCode`, `day` or `reason`, 409
 *   when the day is closed already, and 403 for anyone but an administrator.
 */
export function addClosureDay(body: NewClosureRequest): Promise<ClosureDay> {
  return api.post(CLOSURE_DAYS_ENDPOINT, body, readClosureDay)
}

/**
 * POST /api/admin/closure-days/{id}/cancel. Opens the day again and answers
 * with the closure, cancelled.
 *
 * @throws ApiError with status 404 when no closure has the key, 409 when it was
 *   cancelled already, and 403 for anyone but an administrator.
 */
export function cancelClosureDay(id: string): Promise<ClosureDay> {
  return api.post(`${CLOSURE_DAYS_ENDPOINT}/${encodeURIComponent(id)}/cancel`, undefined, readClosureDay)
}
