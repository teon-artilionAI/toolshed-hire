/**
 * The returns and settlement wire types.
 *
 * Taking equipment back, recording a unit as lost, paying a balance, and the
 * two lists of hires, one for the counter and one for the customer. Every one
 * of these routes answers with a `Rental`, or a page of them, and that type is
 * built from the generated schema in contract-counter.ts like every other.
 *
 * The bodies and the queries here are written by hand. The OpenAPI document the
 * backend commits does not describe these routes yet, so there is nothing to
 * build them from. Each one follows the contract for this change word for word,
 * and when the document gains the routes these become refinements of the
 * generated shapes, the way the other contract modules are written, and any
 * difference stops the application compiling.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { ConditionGrade, Rental, RentalStatus } from './contract-counter'

/**
 * One unit coming back, in the body of `POST /api/rentals/{id}/returns`.
 *
 * `hourMeterIn` is a whole number of hours, and null for a unit with no meter.
 * `accessoriesIn` and `notes` are null when there is nothing to record. The
 * screens always send every member, so the body reads the same for each unit.
 * `flaggedForDamage` sends a unit to quarantine even when its grade is no
 * worse than it went out.
 */
export type ReturnItemRequest = {
  rentalItemId: string
  conditionIn: ConditionGrade
  hourMeterIn: number | null
  accessoriesIn: string | null
  notes: string | null
  flaggedForDamage: boolean
}

/**
 * The body `POST /api/rentals/{id}/returns` accepts. One or more units that
 * are still out, each once. The API refuses a unit already back with a 409 and
 * a unit that is not on the hire with a 422.
 */
export type ReturnRequest = {
  items: ReturnItemRequest[]
}

/**
 * The body `POST /api/rentals/{id}/balance-payment` accepts. The reference of
 * the payment the customer made at the counter, 1 to 40 characters. The
 * payment is simulated, and nothing reaches a bank.
 */
export type BalancePaymentRequest = {
  paymentReference: string
}

/**
 * The query `GET /api/rentals` accepts, for staff.
 *
 * Every filter may be left out. `overdueOnly` keeps only the hires with a unit
 * out past its due date. `page` counts from 1 and `pageSize` is 1 to 50. The
 * screens always send the page and its size, so here both are required.
 */
export type RentalListQuery = {
  branchCode?: string
  status?: RentalStatus
  overdueOnly?: boolean
  customerProfileId?: string
  page: number
  pageSize: number
}

/** The query `GET /api/me/rentals` accepts. The customer's own hires only. */
export type MyRentalsQuery = {
  page: number
  pageSize: number
}

/**
 * A page of hires, from `GET /api/rentals` for staff, most overdue first and
 * then newest, and from `GET /api/me/rentals` for a customer, newest first.
 * A customer's hires carry no asset tag on any unit.
 */
export type RentalPage = {
  items: Rental[]
  page: number
  pageSize: number
  total: number
}
