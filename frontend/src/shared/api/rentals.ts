/**
 * The hire routes. Reading a hire, taking its units back, recording a unit as
 * lost, paying a balance, and the two lists of hires.
 *
 * Every write is for staff at the branch the hire went out from, and answers
 * with the whole hire as the server now has it. The late fees, the charges, the
 * deposit held, withheld and released and the balance due are all the server's,
 * worked out in the same transaction as the write. Nothing here or above it
 * adds, multiplies or rounds a figure.
 *
 * A write is sent once for each press of a button. The client never repeats a
 * POST by itself, because a request that timed out may still have reached the
 * server and settled the deposit.
 */

import { api } from './client'
import type {
  BalancePaymentRequest,
  MyRentalsQuery,
  Rental,
  RentalListQuery,
  RentalPage,
  ReturnRequest,
} from './contract'
import { readCount, readList, readObject } from './read'
import { readRental } from './rental-read'

const RENTALS_ENDPOINT = '/rentals'
const MY_RENTALS_ENDPOINT = '/me/rentals'

/**
 * How many whole days past due a unit has to be before it can be recorded as
 * lost. A unit more than this late goes to the escalation queue (BR-31).
 */
export const LOSS_AFTER_DAYS_LATE = 14

/** The longest payment reference the balance payment route takes. */
export const MAX_PAYMENT_REFERENCE_LENGTH = 40

/** The page size the lists of hires ask for. The API's own default. */
export const RENTAL_PAGE_SIZE = 20

function readRentalPage(value: unknown, path: string): RentalPage {
  const record = readObject(value, path, 'a page of hires')
  return {
    items: readList(record, 'items', path, readRental),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/** A key or a reference is user input by the time it reaches here, so it is
 *  always encoded. */
function rentalEndpoint(idOrReference: string): string {
  return `${RENTALS_ENDPOINT}/${encodeURIComponent(idOrReference)}`
}

/**
 * GET /api/rentals/{id}, where the id is the key or the reference.
 *
 * @throws ApiError with status 404 when there is no such hire.
 */
export function getRental(idOrReference: string, signal?: AbortSignal): Promise<Rental> {
  return api.get(rentalEndpoint(idOrReference), readRental, { signal })
}

/**
 * GET /api/rentals. The hires that match, most overdue first and then newest.
 * The server moves a hire with a unit past its due date to overdue before it
 * answers.
 */
export function listRentals(query: RentalListQuery, signal?: AbortSignal): Promise<RentalPage> {
  return api.get(RENTALS_ENDPOINT, readRentalPage, { query, signal })
}

/**
 * GET /api/me/rentals. The signed in customer's own hires, newest first, with
 * no asset tag on any unit.
 *
 * @throws ApiError with status 403 for a member of staff. No staff screen asks.
 */
export function listMyRentals(query: MyRentalsQuery, signal?: AbortSignal): Promise<RentalPage> {
  return api.get(MY_RENTALS_ENDPOINT, readRentalPage, { query, signal })
}

/**
 * POST /api/rentals/{id}/returns. Takes one or more units back.
 *
 * @throws ApiError with status 409 when a unit is already back, 403 at another
 *   branch, and 422 when a unit is not on this hire or a value is refused.
 */
export function returnItems(idOrReference: string, body: ReturnRequest): Promise<Rental> {
  return api.post(`${rentalEndpoint(idOrReference)}/returns`, body, readRental)
}

/**
 * POST /api/rentals/{id}/items/{itemId}/loss. No body.
 *
 * Charges fourteen days of late fee, forfeits the deposit for the unit, raises
 * a recovery charge up to its replacement value and marks the unit lost.
 *
 * @throws ApiError with status 409 when the unit is not that late or is back,
 *   and 403 at another branch.
 */
export function recordLoss(idOrReference: string, itemId: string): Promise<Rental> {
  const endpoint = `${rentalEndpoint(idOrReference)}/items/${encodeURIComponent(itemId)}/loss`
  return api.post(endpoint, undefined, readRental)
}

/**
 * POST /api/rentals/{id}/balance-payment. Records the simulated payment of the
 * balance due, which settles the hire.
 *
 * @throws ApiError with status 409 when nothing is due, 403 at another branch,
 *   and 422 when the reference is refused.
 */
export function payBalance(idOrReference: string, paymentReference: string): Promise<Rental> {
  const body: BalancePaymentRequest = { paymentReference }
  return api.post(`${rentalEndpoint(idOrReference)}/balance-payment`, body, readRental)
}
