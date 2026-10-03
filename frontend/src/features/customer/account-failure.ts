/**
 * What to say when a registration or account request does not work.
 *
 * There are four answers. The API refused what was sent and named the fields.
 * The caller has asked too often and must wait. The link that was followed is
 * no longer good. Everything else is a fault, and the shared error state words
 * that.
 *
 * None of these says whether an email address has an account. The API does not
 * tell the browser, and nothing here guesses.
 */

import { isApiError } from '../../shared/api-problem'
import { fieldErrorsFromProblem, isRefusal } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { problemTypeEndsWith } from '../../shared/api/session-seam'
import { waitInWords } from './sign-in-failure'

const HTTP_BAD_REQUEST = 400
const HTTP_TOO_MANY_REQUESTS = 429

export type AccountFailure =
  /** A 422. Each refused field has a sentence, and `detail` is the server's summary. */
  | { kind: 'refused'; detail: string; fields: FieldErrors }
  /** A 429. The message says how long to wait. */
  | { kind: 'wait'; message: string }
  /** The link was unknown, already used or too old. The API does not say which. */
  | { kind: 'linkInvalid' }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

/**
 * Sort a failed request into one of the answers above.
 *
 * @param error Whatever the request threw.
 * @param invalidLinkType How the problem `type` ends when the link is no
 *   longer good. Leave it out for a request that carries no link token.
 */
export function describeAccountFailure(error: unknown, invalidLinkType?: string): AccountFailure {
  if (!isApiError(error)) return { kind: 'fault', error }
  if (error.status === HTTP_TOO_MANY_REQUESTS) {
    return {
      kind: 'wait',
      message: `There have been too many attempts. Wait ${waitInWords(
        error.retryAfterSeconds,
      )} and try again.`,
    }
  }
  if (
    invalidLinkType !== undefined &&
    error.status === HTTP_BAD_REQUEST &&
    problemTypeEndsWith(error, invalidLinkType)
  ) {
    return { kind: 'linkInvalid' }
  }
  if (isRefusal(error)) {
    return { kind: 'refused', detail: error.detail, fields: fieldErrorsFromProblem(error) }
  }
  return { kind: 'fault', error }
}
