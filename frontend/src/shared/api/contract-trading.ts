/**
 * The wire types of the owner's trading calendar, the closed days and the
 * closure days.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * The generated types say less than the server does in two ways, and the types
 * below say it exactly. A day and an instant are generated as a plain string,
 * and here each carries the name of what it is. And the generated body of a
 * new closure lets the branch be left out, which the screen never does. It
 * sends a branch code or null for every branch, so here the member is required.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { BodyOf, CreatedJsonOf, IsoDate, IsoTimestamp, JsonOf, Paths, QueryOf, Refine } from './contract-kit'

type ClosureDaysRoute = Paths['/api/admin/closure-days']
type ImpactRoute = Paths['/api/admin/closure-days/impact']
type CancelRoute = Paths['/api/admin/closure-days/{id}/cancel']

/**
 * One day the owner's list shows as closed. `GET /api/admin/closure-days`.
 *
 * `kind` is `public_holiday` for a holiday the server worked out from the
 * Public Holidays Act, listed once with `branchCode` null because it closes
 * every branch, and `closure` for a day the owner closed. `branchCode` is null
 * for a closure of every branch. `closureId` is the key a closure is cancelled
 * by, and null for a holiday, which nobody can cancel.
 */
export type CalendarClosedDay = Refine<JsonOf<ClosureDaysRoute['get']>['items'][number], { day: IsoDate }>

/** `GET /api/admin/closure-days`. Every holiday and live closure in the span, by day. */
export type CalendarClosedDays = Refine<JsonOf<ClosureDaysRoute['get']>, { items: CalendarClosedDay[] }>

/**
 * The query `GET /api/admin/closure-days` accepts. Both days may be left out,
 * and the span then runs from today for a year. A span longer than a year, or
 * one that ends before it starts, is refused with a 422 naming `to`.
 */
export type CalendarQuery = QueryOf<ClosureDaysRoute['get']>

/**
 * One closure day, as it was added or as it is once cancelled. A new closure
 * answers this with a 201, and a cancellation with a 200, so it is built from
 * both. `cancelledAt` is null while the closure is live.
 */
export type ClosureDay = Refine<
  CreatedJsonOf<ClosureDaysRoute['post']> & JsonOf<CancelRoute['post']>,
  { day: IsoDate; createdAt: IsoTimestamp; cancelledAt: IsoTimestamp | null }
>

/**
 * The body `POST /api/admin/closure-days` accepts. A branch code, or null to
 * close every branch, the day, and the reason customers read, one to one
 * hundred and twenty characters. A day before today or more than a year ahead
 * is refused with a 422 naming `day`, a branch that is not trading with one
 * naming `branchCode`, and a day already closed at that branch or at every
 * branch with a 409.
 */
export type NewClosureRequest = Refine<BodyOf<ClosureDaysRoute['post']>, { branchCode: string | null }>

/** The query `GET /api/admin/closure-days/impact` accepts. The day, and the
 *  branch, which is left out for every branch. */
export type ClosureImpactQuery = QueryOf<ImpactRoute['get']>

/**
 * A booking or a hire out that falls on the day about to close. `hireDay` is
 * `collection` when a held or confirmed booking starts that day, `return` when
 * it ends that day, and `due_back` when the equipment of a hire still out is
 * due back that day. A hire carries its own reference, and `from` is the day it
 * was collected. A new closure never changes any of them. The owner rings the
 * customer.
 */
export type StrandedBooking = Refine<JsonOf<ImpactRoute['get']>['items'][number], { from: IsoDate; to: IsoDate }>

/** `GET /api/admin/closure-days/impact`. At most two hundred bookings, and how
 *  many there are in all. */
export type ClosureImpact = Refine<JsonOf<ImpactRoute['get']>, { items: StrandedBooking[] }>
