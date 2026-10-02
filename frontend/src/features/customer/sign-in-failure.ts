/**
 * What to say when a sign in does not work.
 *
 * There are three answers and no more. A refusal gets one sentence that is
 * the same whatever the reason. The API does not say whether the address was
 * unknown, the password was wrong or the account is locked, and this screen
 * must not guess, because a different sentence for each would tell a stranger
 * which addresses have accounts. Too many attempts gets the wait the API
 * named. Everything else is a fault, and the shared error state words it.
 */

import { isApiError } from '../../shared/api-problem'
import { TOO_MANY_ATTEMPTS } from '../../shared/api/auth'
import { problemTypeEndsWith } from '../../shared/api/session-seam'

const HTTP_UNAUTHORIZED = 401
const HTTP_TOO_MANY_REQUESTS = 429
const SECONDS_PER_MINUTE = 60

/** The one sentence for every refused sign in. */
export const REFUSED_MESSAGE =
  'That email address and password do not match an account. Check them both and try again.'

export type SignInFailure =
  /** The API refused the sign in. Shown as one generic sentence. */
  | { kind: 'refused'; message: string }
  /** Too many attempts. The message says how long to wait. */
  | { kind: 'wait'; message: string }
  /** The API could not be reached, or something else went wrong. */
  | { kind: 'fault'; error: unknown }

/**
 * How long to wait, in words.
 *
 * @param seconds The wait from `Retry-After`, or null when the API named none.
 * @returns Seconds below a minute, and whole minutes rounded up above it, so
 *   the person is never told a time that is shorter than the real one.
 */
export function waitInWords(seconds: number | null): string {
  if (seconds === null) return 'a few minutes'
  if (seconds < SECONDS_PER_MINUTE) return seconds === 1 ? '1 second' : `${seconds} seconds`
  const minutes = Math.ceil(seconds / SECONDS_PER_MINUTE)
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

/**
 * Sort a failed sign in into one of the three answers.
 *
 * @param error Whatever the sign in threw.
 */
export function describeSignInFailure(error: unknown): SignInFailure {
  if (isApiError(error)) {
    if (error.status === HTTP_TOO_MANY_REQUESTS || problemTypeEndsWith(error, TOO_MANY_ATTEMPTS)) {
      return {
        kind: 'wait',
        message: `There have been too many sign in attempts. Wait ${waitInWords(
          error.retryAfterSeconds,
        )} and try again.`,
      }
    }
    if (error.status === HTTP_UNAUTHORIZED) return { kind: 'refused', message: REFUSED_MESSAGE }
  }
  return { kind: 'fault', error }
}
