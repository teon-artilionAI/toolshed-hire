/**
 * What to say when a booking confirmation cannot be sent again.
 *
 * The API allows three re-sends of one booking in an hour. The fourth is a
 * 429 with `Retry-After`, and that is a plain limit rather than a fault. It
 * gets its own words, with the wait the API named. Every other failure stays
 * with the shared error state, which keeps server and provider details out of
 * the screen.
 */

import { TOO_MANY_ATTEMPTS } from './api/auth'
import { isApiError } from './api-problem'
import { problemTypeEndsWith } from './api/session-seam'
import { waitInWords } from './wait-words'

const HTTP_TOO_MANY_REQUESTS = 429

const RESEND_LIMIT =
  'This booking has had its confirmation sent again three times in the last hour.'

export type ResendFailure =
  /** The hourly limit. The message says how long to wait. */
  | { kind: 'wait'; message: string; reference: string | null }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

/**
 * Sort a failed re-send into the hourly limit or an ordinary fault.
 *
 * @param error Whatever the re-send threw.
 */
export function describeResendFailure(error: unknown): ResendFailure {
  if (
    isApiError(error) &&
    (error.status === HTTP_TOO_MANY_REQUESTS || problemTypeEndsWith(error, TOO_MANY_ATTEMPTS))
  ) {
    return {
      kind: 'wait',
      message: `${RESEND_LIMIT} Wait ${waitInWords(error.retryAfterSeconds)} and try again.`,
      reference: error.requestId,
    }
  }
  return { kind: 'fault', error }
}
