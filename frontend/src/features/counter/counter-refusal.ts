/**
 * What to say when a counter request does not work.
 *
 * The counter routes refuse in four ways an assistant can do something about,
 * and each gets its own answer on the screen. Everything else is a fault, and
 * the shared error state words that.
 *
 * Where the answer is a sentence, it is the server's sentence, read from the
 * problem document. A 409 on a hold names the model and the dates that could
 * not be supplied, and a 409 on a handover says whether the booking is not
 * confirmed or starts later. The browser knows neither, so it shows what it
 * was sent. A failure that carries no problem document is a fault.
 */

import { isApiError } from '../../shared/api-problem'
import { fieldErrorsFromProblem, isRefusal } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ACCOUNT_ON_HOLD } from '../../shared/api/reservations'
import { problemTypeEndsWith } from '../../shared/api/session-seam'

const HTTP_FORBIDDEN = 403
const HTTP_NOT_FOUND = 404
const HTTP_CONFLICT = 409

export type CounterRefusal =
  /** The equipment could not be held, or the move is no longer allowed. */
  | { kind: 'conflict'; detail: string }
  /** The customer's account is on hold and may not book. */
  | { kind: 'accountOnHold'; detail: string }
  /** Refused for another reason the server names, such as another branch. */
  | { kind: 'forbidden'; detail: string }
  /** A field was refused, and each refused field has a sentence. */
  | { kind: 'refused'; detail: string; fields: FieldErrors }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

/**
 * Sort a failed counter request into one of the answers above.
 *
 * @param error Whatever the request threw.
 */
export function describeCounterFailure(error: unknown): CounterRefusal {
  if (!isApiError(error) || error.problem === null) return { kind: 'fault', error }
  const { detail } = error.problem
  if (error.status === HTTP_CONFLICT) return { kind: 'conflict', detail }
  if (error.status === HTTP_FORBIDDEN && problemTypeEndsWith(error, ACCOUNT_ON_HOLD)) {
    return { kind: 'accountOnHold', detail }
  }
  if (error.status === HTTP_FORBIDDEN) return { kind: 'forbidden', detail }
  if (isRefusal(error)) return { kind: 'refused', detail, fields: fieldErrorsFromProblem(error) }
  return { kind: 'fault', error }
}

/** Whether a read failed because there is nothing with that key or reference. */
export function isNotFound(error: unknown): boolean {
  return isApiError(error) && error.status === HTTP_NOT_FOUND
}

/**
 * Whether a customer read from the address is not on file.
 *
 * The key comes from the address, which anybody can write. The API answers a
 * key it does not know with a 404 and something that is not a key at all with
 * a 422, and to the assistant both mean the same thing.
 */
export function isNotOnFile(error: unknown): boolean {
  return isNotFound(error) || isRefusal(error)
}
