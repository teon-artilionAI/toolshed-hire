/**
 * The checkout routes, where a confirmed reservation becomes a hire.
 *
 * Two calls, both for staff. One reads what the counter needs to hand the
 * equipment over, and the other records the handover. Both take the key of the
 * reservation or its reference.
 *
 * The handover is sent once for each press of the button and never repeated by
 * the client. The API answers a repeat for a reservation that is already out
 * with the hire it made the first time and writes nothing, so a person who
 * presses again after a timeout is shown the same hire.
 */

import { ACCOUNT_STATUSES, ID_DOCUMENT_TYPES } from './account'
import { api } from './client'
import type {
  CheckoutCustomer,
  CheckoutRequest,
  CheckoutUnit,
  Rental,
  ReservationCheckout,
} from './contract'
import {
  readCount,
  readDate,
  readFlag,
  readList,
  readMoney,
  readNullableCount,
  readNullableText,
  readObject,
  readOneOf,
  readText,
} from './read'
import { CONDITION_GRADES, readRental } from './rental-read'
import { RESERVATION_STATUSES } from './reservations'

/** The longest note about accessories the API keeps for one unit. */
export const MAX_ACCESSORIES_LENGTH = 200

function readCheckoutCustomer(value: unknown, path: string): CheckoutCustomer {
  const record = readObject(value, path, 'the customer of a checkout')
  return {
    id: readText(record, 'id', path),
    displayName: readText(record, 'displayName', path),
    phone: readText(record, 'phone', path),
    idDocumentType: readOneOf(record, 'idDocumentType', path, ID_DOCUMENT_TYPES),
    idDocumentLast4: readText(record, 'idDocumentLast4', path),
    accountStatus: readOneOf(record, 'accountStatus', path, ACCOUNT_STATUSES),
  }
}

function readCheckoutUnit(value: unknown, path: string): CheckoutUnit {
  const record = readObject(value, path, 'a unit to check out')
  return {
    allocationId: readText(record, 'allocationId', path),
    assetTag: readText(record, 'assetTag', path),
    modelName: readText(record, 'modelName', path),
    modelSlug: readText(record, 'modelSlug', path),
    conditionGrade: readOneOf(record, 'conditionGrade', path, CONDITION_GRADES),
    hourMeter: readNullableCount(record, 'hourMeter', path),
    depositPerUnit: readMoney(record, 'depositPerUnit', path),
  }
}

function readCheckout(value: unknown, path: string): ReservationCheckout {
  const record = readObject(value, path, 'a checkout')
  return {
    reservationId: readText(record, 'reservationId', path),
    reference: readText(record, 'reference', path),
    status: readOneOf(record, 'status', path, RESERVATION_STATUSES),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    customer: readCheckoutCustomer(record.customer, path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    hireDays: readCount(record, 'hireDays', path),
    units: readList(record, 'units', path, readCheckoutUnit),
    hireTotalIncVat: readMoney(record, 'hireTotalIncVat', path),
    depositTotal: readMoney(record, 'depositTotal', path),
    canCheckOut: readFlag(record, 'canCheckOut', path),
    refusal: readNullableText(record, 'refusal', path),
    rentalId: readNullableText(record, 'rentalId', path),
  }
}

/** A key or a reference is user input by the time it reaches here, so it is
 *  always encoded. */
function checkoutEndpoint(idOrReference: string): string {
  return `/reservations/${encodeURIComponent(idOrReference)}/checkout`
}

/**
 * GET /api/reservations/{id}/checkout.
 *
 * @throws ApiError with status 404 when there is no such reservation.
 */
export function getCheckout(idOrReference: string, signal?: AbortSignal): Promise<ReservationCheckout> {
  return api.get(checkoutEndpoint(idOrReference), readCheckout, { signal })
}

/**
 * POST /api/reservations/{id}/checkout. 201 with the new hire, or 200 with the
 * hire that was made before when the reservation is already out.
 *
 * @throws ApiError with status 409 when the reservation is not confirmed or
 *   starts later, 403 at another branch, and 422 when an allocation is missing
 *   or repeated or the agreement is not signed.
 */
export function checkOutReservation(idOrReference: string, body: CheckoutRequest): Promise<Rental> {
  return api.post(checkoutEndpoint(idOrReference), body, readRental)
}
