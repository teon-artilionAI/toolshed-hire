/**
 * The API answered by the spec itself, for the owner's trading calendar, the
 * view of SC-19 at /admin/closure-days.
 *
 * The accessibility scan and the narrow screen check of the calendar need a
 * year of closed days and the bookings a closure would strand. They answer
 * beside the dashboard and the report in admin-answers.ts, with a reason as
 * long as the server keeps and long customer names, which are what break a
 * layout. Every day is counted from today, so the list reads the same whenever
 * the run is.
 */

import { dateFromToday } from './hire-dates.ts'

/** The heading of the trading calendar. */
export const CALENDAR_HEADING = 'Trading calendar'

/** The reason of the Bellville closure, as long as the server keeps a reason. */
export const LONG_REASON = 'Stocktake and annual count of every unit in the yard, the workshop and the hire floor, done by the team.'

/** The key of the Bellville closure the scans cancel. */
export const BELLVILLE_CLOSURE_ID = '7c1d2e3f-0000-4a2b-9c3d-000000000020'

/** The day the scans close at Cape Town CBD, three weeks from today. */
export const DAY_TO_CLOSE = dateFromToday(21)

/** The closed days of the next twelve months, by day. */
export function closedDays() {
  return [
    { day: dateFromToday(8), branchCode: 'BLV', reason: LONG_REASON, kind: 'closure', closureId: BELLVILLE_CLOSURE_ID },
    { day: dateFromToday(40), branchCode: null, reason: 'Day of Reconciliation', kind: 'public_holiday', closureId: null },
    {
      day: dateFromToday(95),
      branchCode: null,
      reason: 'Election day, declared by the government',
      kind: 'closure',
      closureId: '7c1d2e3f-0000-4a2b-9c3d-000000000095',
    },
  ]
}

/** What a closure of `DAY_TO_CLOSE` at Cape Town CBD strands. A booking brought
 *  back that day, a hire still out and due back that day, and a booking
 *  collected that day. */
export const STRANDED = {
  items: [
    {
      reference: 'TSH-R-26-000127',
      branchCode: 'CBD',
      customerName: 'Bartholomew Christiaan van der Westhuizen-Mokoena',
      customerPhone: '082 441 7719',
      from: dateFromToday(17),
      to: DAY_TO_CLOSE,
      hireDay: 'return',
    },
    {
      reference: 'TSH-H-26-000098',
      branchCode: 'CBD',
      customerName: 'Marius Pretorius-Vanderwesthuizen Construction and Plant Hire',
      customerPhone: '083 555 0123',
      from: dateFromToday(18),
      to: DAY_TO_CLOSE,
      hireDay: 'due_back',
    },
    {
      reference: 'TSH-R-26-000131',
      branchCode: 'CBD',
      customerName: 'Nomvuyiso Thandiwe Mahlangu-Vanderbijl',
      customerPhone: '021 555 0199',
      from: DAY_TO_CLOSE,
      to: dateFromToday(24),
      hireDay: 'collection',
    },
  ],
  total: 3,
}

/** The closure the server answers with once Cape Town CBD is closed on the day. */
export const CBD_CLOSURE = {
  id: '7c1d2e3f-0000-4a2b-9c3d-000000000021',
  branchCode: 'CBD',
  day: DAY_TO_CLOSE,
  reason: 'Stocktake',
  createdAt: '2026-10-13T08:00:00+02:00',
  cancelledAt: null,
}

/** The answers the calendar reads, for the scans that only open it. */
export const CALENDAR_ANSWERS: Record<string, unknown> = {
  'GET /api/admin/closure-days': { items: closedDays() },
  'GET /api/admin/closure-days/impact': STRANDED,
}
