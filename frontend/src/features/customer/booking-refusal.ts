/**
 * What to say when a booking request does not work.
 *
 * The reservation routes refuse in four ways that a person can do something
 * about, and each gets its own answer on the screen. Everything else is a
 * fault, and the shared error state words that.
 *
 * Where the answer is a sentence, it is the server's sentence. A 409 names the
 * model and the dates that could not be supplied, and the browser has no way
 * of knowing either, so it shows what it was sent. A sentence is only ever
 * taken from a problem document. A failure that carries none is a fault.
 */

import { isApiError } from '../../shared/api-problem'
import { fieldErrorsFromProblem, isRefusal } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ACCOUNT_ON_HOLD, EMAIL_NOT_VERIFIED } from '../../shared/api/reservations'
import { problemTypeEndsWith } from '../../shared/api/session-seam'

const HTTP_FORBIDDEN = 403
const HTTP_NOT_FOUND = 404
const HTTP_CONFLICT = 409

export type BookingRefusal =
  /** The equipment could not be held, or the move is no longer allowed. */
  | { kind: 'conflict'; detail: string }
  /** The customer's account is on hold and may not book. */
  | { kind: 'accountOnHold'; detail: string }
  /** The customer has not verified their email address. */
  | { kind: 'emailNotVerified' }
  /** The dates, the branch, a line or the reason were refused. */
  | { kind: 'refused'; detail: string; fields: FieldErrors }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

/**
 * Sort a failed booking request into one of the answers above.
 *
 * @param error Whatever the request threw.
 */
export function describeBookingFailure(error: unknown): BookingRefusal {
  if (!isApiError(error) || error.problem === null) return { kind: 'fault', error }
  const { detail } = error.problem
  if (error.status === HTTP_CONFLICT) return { kind: 'conflict', detail }
  if (error.status === HTTP_FORBIDDEN && problemTypeEndsWith(error, ACCOUNT_ON_HOLD)) {
    return { kind: 'accountOnHold', detail }
  }
  if (error.status === HTTP_FORBIDDEN && problemTypeEndsWith(error, EMAIL_NOT_VERIFIED)) {
    return { kind: 'emailNotVerified' }
  }
  if (isRefusal(error)) return { kind: 'refused', detail, fields: fieldErrorsFromProblem(error) }
  return { kind: 'fault', error }
}

/** Whether a read failed because there is nothing at that address. For a
 *  reservation that is also the answer when it belongs to somebody else. The
 *  API does not say which. */
export function isNotFound(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_NOT_FOUND
}
