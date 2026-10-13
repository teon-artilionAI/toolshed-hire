/**
 * The owner's trading calendar for tests, shaped the way the contract for the
 * closed days and the closure days describes them.
 *
 * Two closures and two public holidays across March, April and May 2026 at the
 * pinned day, Thursday 12 March. A stocktake at Bellville, Human Rights Day and
 * Good Friday, which close every branch, and an election day the owner closed
 * every branch for. Two bookings that a closure of Friday 27 March would
 * strand, one collected and one brought back that day, and a hire out that is
 * due back that day.
 */

import type { CalendarClosedDay, CalendarClosedDays, ClosureDay, ClosureImpact, StrandedBooking } from '../shared/api/contract'

export const CALENDAR_ROUTE = 'GET /api/admin/closure-days'
export const IMPACT_ROUTE = 'GET /api/admin/closure-days/impact'
export const ADD_CLOSURE_ROUTE = 'POST /api/admin/closure-days'

export function cancelClosureRoute(id: string): string {
  return `POST /api/admin/closure-days/${id}/cancel`
}

/** The day a test closes, a Friday the branches would trade. */
export const DAY_TO_CLOSE = '2026-03-27'

export const STOCKTAKE: CalendarClosedDay = {
  day: '2026-03-20',
  branchCode: 'BLV',
  reason: 'Stocktake',
  kind: 'closure',
  closureId: '7c1d2e3f-0000-4a2b-9c3d-000000000020',
}

export const HUMAN_RIGHTS_DAY: CalendarClosedDay = {
  day: '2026-03-21',
  branchCode: null,
  reason: 'Human Rights Day',
  kind: 'public_holiday',
  closureId: null,
}

export const GOOD_FRIDAY: CalendarClosedDay = {
  day: '2026-04-03',
  branchCode: null,
  reason: 'Good Friday',
  kind: 'public_holiday',
  closureId: null,
}

export const ELECTION_DAY: CalendarClosedDay = {
  day: '2026-05-27',
  branchCode: null,
  reason: 'Election day, declared by the government',
  kind: 'closure',
  closureId: '7c1d2e3f-0000-4a2b-9c3d-000000000527',
}

export function calendarOf(
  items: CalendarClosedDay[] = [STOCKTAKE, HUMAN_RIGHTS_DAY, GOOD_FRIDAY, ELECTION_DAY],
): CalendarClosedDays {
  return { items }
}

/** A booking collected at Cape Town CBD on the day a test closes. */
export const COLLECTING: StrandedBooking = {
  reference: 'TSH-R-26-000131',
  branchCode: 'CBD',
  customerName: 'Nomsa Dlamini',
  customerPhone: '082 441 7719',
  from: DAY_TO_CLOSE,
  to: '2026-03-30',
  hireDay: 'collection',
}

/** A booking brought back to Cape Town CBD on the day a test closes. */
export const RETURNING: StrandedBooking = {
  reference: 'TSH-R-26-000127',
  branchCode: 'CBD',
  customerName: 'Sipho Ndlovu',
  customerPhone: '021 555 0199',
  from: '2026-03-23',
  to: DAY_TO_CLOSE,
  hireDay: 'return',
}

/** A hire collected at Cape Town CBD before the day, and still out, due back on it. */
export const DUE_BACK: StrandedBooking = {
  reference: 'TSH-H-26-000098',
  branchCode: 'CBD',
  customerName: 'Wesley Adonis',
  customerPhone: '083 555 0123',
  from: '2026-03-24',
  to: DAY_TO_CLOSE,
  hireDay: 'due_back',
}

export function impactOf(
  items: StrandedBooking[] = [RETURNING, DUE_BACK, COLLECTING],
  total = items.length,
): ClosureImpact {
  return { items, total }
}

/** The closure the server answers with once Cape Town CBD is closed on the day. */
export const CBD_CLOSURE: ClosureDay = {
  id: '7c1d2e3f-0000-4a2b-9c3d-000000000327',
  branchCode: 'CBD',
  day: DAY_TO_CLOSE,
  reason: 'Stocktake',
  createdAt: '2026-03-12T08:00:00+02:00',
  cancelledAt: null,
}
