/**
 * What to say to a person when something fails.
 *
 * An `ApiError` carries a title and a detail written for whoever is debugging.
 * They name paths, statuses and proxies, and none of that belongs in front of a
 * customer. So the words on the screen are chosen here, from the kind of
 * failure alone, and the technical detail stays in the console and the log.
 *
 * The one thing I do pass through is the request id. It means nothing by
 * itself, and it lets a person quote one value that leads me to the log lines.
 */

import { isApiError } from './api-problem'

export interface FailureWords {
  /** What to do about it, as one or two plain sentences. */
  advice: string
  /** The id to quote, or null when the failure never reached the server. */
  reference: string | null
}

const UNREACHABLE_ADVICE =
  'We could not reach Toolshed Hire. Check your connection and try again.'

const FAULT_ADVICE =
  'Something went wrong on our side. Try again in a moment, and ring your branch if it keeps happening.'

/**
 * Choose the words for a failure.
 *
 * @param error Whatever was thrown. It does not have to be an `ApiError`.
 * @returns Advice in plain words and the reference to quote, if there is one.
 *   Never the raw message, the status code or a stack.
 */
export function failureWords(error: unknown): FailureWords {
  if (isApiError(error)) {
    return {
      advice: error.isBackendUnreachable ? UNREACHABLE_ADVICE : FAULT_ADVICE,
      reference: error.requestId,
    }
  }
  return { advice: FAULT_ADVICE, reference: null }
}
