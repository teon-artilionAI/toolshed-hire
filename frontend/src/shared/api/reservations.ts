/**
 * The reservation endpoints.
 *
 * Six routes, all of which need a signed in person. A customer creates a
 * reservation as a draft, puts it on hold, confirms it, cancels it, lists
 * their own and reads one. Each function here makes one call and reads the
 * body into its contract type.
 *
 * Every route answers with the whole reservation, and every figure in it is
 * the server's. So are `canHold`, `canConfirm` and `canCancel`, which say what
 * this person may do to it right now. Nothing here or above it decides that.
 *
 * A write is sent once. The client never repeats a POST by itself, because a
 * request that timed out may still have reached the server.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  CancelReservationRequest,
  CreateReservationRequest,
  Reservation,
  ReservationLine,
  ReservationListQuery,
  ReservationPage,
  ReservationStatus,
} from './contract'
import {
  readCount,
  readDate,
  readFlag,
  readList,
  readMoney,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readPercent,
  readText,
} from './read'

const RESERVATIONS_ENDPOINT = '/reservations'

/** Every status a reservation can be in, in the order a filter lists them. */
export const RESERVATION_STATUSES: readonly ReservationStatus[] = [
  'DRAFT',
  'HELD',
  'CONFIRMED',
  'COLLECTED',
  'RETURNED',
  'CANCELLED',
  'NO_SHOW',
  'EXPIRED',
]

/** The page size the API uses when a request does not name one. */
export const DEFAULT_RESERVATION_PAGE_SIZE = 20

/** The longest reason a cancellation may carry. */
export const MAX_CANCELLATION_REASON_LENGTH = 200

/** How the `type` of the 403 ends when the customer's account is on hold. */
export const ACCOUNT_ON_HOLD = 'account-on-hold'

/** How the `type` of the 403 ends when the customer has not verified their email. */
export const EMAIL_NOT_VERIFIED = 'email-not-verified'

function readAssetTag(value: unknown, path: string): string {
  if (typeof value !== 'string') {
    throw malformedResponse(path, `Expected every asset tag from ${path} to be text.`)
  }
  return value
}

function readReservationLine(value: unknown, path: string): ReservationLine {
  const record = readObject(value, path, 'a reservation line')
  return {
    modelSlug: readText(record, 'modelSlug', path),
    modelName: readText(record, 'modelName', path),
    quantity: readCount(record, 'quantity', path),
    dailyRate: readMoney(record, 'dailyRate', path),
    weeklyRate: readMoney(record, 'weeklyRate', path),
    depositPerUnit: readMoney(record, 'depositPerUnit', path),
    lineSubtotalExVat: readMoney(record, 'lineSubtotalExVat', path),
    allocatedCount: readCount(record, 'allocatedCount', path),
    assetTags: readList(record, 'assetTags', path, readAssetTag),
  }
}

/** When the reservation was made. The contract never sends null for it. */
function readCreatedAt(record: Record<string, unknown>, path: string): string {
  const createdAt = readNullableTimestamp(record, 'createdAt', path)
  if (createdAt === null) {
    throw malformedResponse(path, `Expected field createdAt from ${path} to be an instant, got null.`)
  }
  return createdAt
}

function readReservation(value: unknown, path: string): Reservation {
  const record = readObject(value, path, 'a reservation')
  return {
    id: readText(record, 'id', path),
    reference: readText(record, 'reference', path),
    status: readOneOf(record, 'status', path, RESERVATION_STATUSES),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    hireDays: readCount(record, 'hireDays', path),
    lines: readList(record, 'lines', path, readReservationLine),
    subtotalExVat: readMoney(record, 'subtotalExVat', path),
    discountPercent: readPercent(record, 'discountPercent', path),
    vatAmount: readMoney(record, 'vatAmount', path),
    estimatedTotalIncVat: readMoney(record, 'estimatedTotalIncVat', path),
    depositTotal: readMoney(record, 'depositTotal', path),
    holdExpiresAt: readNullableTimestamp(record, 'holdExpiresAt', path),
    confirmedAt: readNullableTimestamp(record, 'confirmedAt', path),
    cancelledAt: readNullableTimestamp(record, 'cancelledAt', path),
    cancellationReason: readNullableText(record, 'cancellationReason', path),
    canHold: readFlag(record, 'canHold', path),
    canConfirm: readFlag(record, 'canConfirm', path),
    canCancel: readFlag(record, 'canCancel', path),
    customerName: readText(record, 'customerName', path),
    createdAt: readCreatedAt(record, path),
  }
}

function readReservationPage(value: unknown, path: string): ReservationPage {
  const record = readObject(value, path, 'a page of reservations')
  return {
    items: readList(record, 'items', path, readReservation),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/** An id or a reference is user input by the time it reaches here, so it is
 *  always encoded. */
function reservationEndpoint(idOrReference: string): string {
  return `${RESERVATIONS_ENDPOINT}/${encodeURIComponent(idOrReference)}`
}

/**
 * POST /api/reservations. Creates a draft and prices it. Nothing is held yet.
 *
 * @throws ApiError with status 422 when the dates, the branch or a line are
 *   refused, and 403 with a type ending `account-on-hold` when the customer's
 *   account may not book.
 */
export function createReservation(body: CreateReservationRequest): Promise<Reservation> {
  return api.post(RESERVATIONS_ENDPOINT, body, readReservation)
}

/**
 * POST /api/reservations/{id}/hold. Takes the equipment for thirty minutes.
 *
 * @throws ApiError with status 409 when a line cannot be given every unit it
 *   asks for. The `detail` names the model and the dates.
 */
export function holdReservation(id: string): Promise<Reservation> {
  return api.post(`${reservationEndpoint(id)}/hold`, undefined, readReservation)
}

/**
 * POST /api/reservations/{id}/confirm.
 *
 * @throws ApiError with status 409 when the hold has run out, and 403 with a
 *   type ending `email-not-verified` when the customer has not verified their
 *   email address.
 */
export function confirmReservation(id: string): Promise<Reservation> {
  return api.post(`${reservationEndpoint(id)}/confirm`, undefined, readReservation)
}

/**
 * POST /api/reservations/{id}/cancellation.
 *
 * @param reason Why, in the customer's words, or null when they gave none.
 * @throws ApiError with status 409 when the reservation can no longer be
 *   cancelled, and 422 when the reason is refused.
 */
export function cancelReservation(id: string, reason: string | null): Promise<Reservation> {
  const body: CancelReservationRequest = { reason }
  return api.post(`${reservationEndpoint(id)}/cancellation`, body, readReservation)
}

/** GET /api/reservations. The caller's own, newest first. */
export function listReservations(
  query: ReservationListQuery,
  signal?: AbortSignal,
): Promise<ReservationPage> {
  return api.get(RESERVATIONS_ENDPOINT, readReservationPage, { query, signal })
}

/**
 * GET /api/reservations/{id}, where the id is the UUID or the reference.
 *
 * @throws ApiError with status 404 when there is no such reservation or it is
 *   not the caller's. The API does not say which.
 */
export function getReservation(idOrReference: string, signal?: AbortSignal): Promise<Reservation> {
  return api.get(reservationEndpoint(idOrReference), readReservation, { signal })
}
