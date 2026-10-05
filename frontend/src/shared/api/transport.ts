/**
 * The one place a request goes out on the wire. Every call to the API reaches
 * `fetch` through this file and through no other.
 *
 * It does the part every call shares. It writes the address and the headers,
 * abandons a request that takes too long, forwards a caller's own abort, logs
 * the start of the call and any failure, and turns a refusal into an
 * `ApiError`. What it does not do is decide what a good answer means. The
 * caller says which media types it accepts and how to take the body of a good
 * answer off the wire, as text for JSON or as bytes for a file, and reads the
 * body itself. client.ts is that caller.
 *
 * The body of a good answer is taken inside the timeout, because a body can
 * stall as easily as a header can.
 */

import { ApiError, errorFromResponse, requestIdFromHeaders } from '../api-problem'
import { logEvent } from './log'
import { buildQueryString } from './query-string'
import type { QueryShape } from './query-string'

/** The one prefix the API is mounted under. Matches `API_PREFIX` in the backend
 *  router assembly and the rewrite source in vercel.json. All three must agree. */
export const API_BASE_PATH = '/api'

/** How long a request may take before it is abandoned. Long enough for a cold
 *  Cloud Run instance that also wakes a suspended database, which took more
 *  than eight seconds on production, and short enough that a dead backend does
 *  not leave a screen waiting with nothing to say. A backend that is down
 *  usually answers at once through the proxy with a gateway error, so only a
 *  backend that hangs waits this long. */
export const REQUEST_TIMEOUT_MS = 15_000

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH'

export interface RequestOptions<Query> {
  /** Members that are undefined, null or empty are left out of the address. */
  query?: Query
  /**
   * Leave the session alone when this call is refused with a 401.
   *
   * Login, refresh and logout set it. A refused login is a wrong password and
   * a refused refresh is the end of the session, and neither is cured by
   * asking for another refresh.
   */
  skipSessionRenewal?: boolean
  /**
   * Statuses whose body carries the answer and not a failure.
   *
   * `/api/health` answers 503 while a dependency is down, and the body of that
   * 503 is the report naming which dependency. Throwing it away and reporting
   * "the request failed" would discard the only useful thing in the response.
   */
  bodyBearingStatuses?: readonly number[]
  /** Lets the caller abandon the request, for example when a screen closes. */
  signal?: AbortSignal
}

/** The path a call is made against, relative by construction. */
export function apiPath(endpoint: string): string {
  return `${API_BASE_PATH}${endpoint}`
}

/** What a call accepts, and how the body of a good answer is taken off the wire. */
export interface Expectation<Body> {
  /** The value of the `Accept` header. */
  accept: string
  /** Takes the body of a good answer. Runs inside the timeout. */
  take: (response: Response) => Promise<Body>
}

/** A response the API answered the call with, and its body as it was taken. */
export interface Answer<Body> {
  response: Response
  body: Body
  requestPath: string
  requestId: string | null
}

/** A good answer with its body, or a refusal with the text it carried. */
type Received<Body> = { answered: true; body: Body } | { answered: false; raw: string }

/**
 * Make one request and hand back the response the API answered with.
 *
 * @param token The bearer token to send, or null to send none.
 * @throws ApiError on a transport failure, a timeout or a non 2xx response
 *   that is not one of `bodyBearingStatuses`. The one exception is a request
 *   the caller abandoned through `signal`. That rethrows the abort untouched,
 *   because it is not a failure and must not be shown as one.
 */
export async function exchange<Body, Query extends QueryShape<Query>>(
  method: HttpMethod,
  endpoint: string,
  expectation: Expectation<Body>,
  options: RequestOptions<Query> & { body?: unknown },
  token: string | null,
): Promise<Answer<Body>> {
  const requestPath = apiPath(endpoint)
  const headers: Record<string, string> = { Accept: expectation.accept }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  // One controller serves both ways a request can be stopped. The timer aborts
  // it when the server is too slow, and the caller's own signal is forwarded to
  // it. I keep the flag so I can tell the two apart afterwards.
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, REQUEST_TIMEOUT_MS)
  const forwardAbort = () => controller.abort()
  if (options.signal?.aborted) controller.abort()
  options.signal?.addEventListener('abort', forwardAbort, { once: true })

  logEvent('info', 'api.request_started', { method, path: requestPath })

  let response: Response
  let received: Received<Body>
  try {
    response = await fetch(`${requestPath}${buildQueryString(options.query)}`, {
      method,
      headers,
      // Same origin by construction, so cookies would travel under the default
      // policy too. I state it because the refresh cookie is the thing the
      // single origin decision exists to protect, and a default that happens to
      // do the right thing is not the same as a decision.
      credentials: 'include',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    })
    // A failed response may carry a problem document, a proxy's own error page
    // or nothing at all, so its body is always read as text and decided on
    // afterwards. A good answer is taken the way the caller asked.
    const answered = response.ok || (options.bodyBearingStatuses?.includes(response.status) ?? false)
    received = answered
      ? { answered: true, body: await expectation.take(response) }
      : { answered: false, raw: await response.text() }
  } catch (cause) {
    if (!timedOut && options.signal?.aborted) {
      logEvent('info', 'api.request_cancelled', { method, path: requestPath })
      throw cause
    }
    const error = new ApiError({
      kind: 'transport',
      status: null,
      title: timedOut ? 'The API did not answer in time' : 'The API could not be reached',
      detail: timedOut
        ? `${method} ${requestPath} was abandoned after ${REQUEST_TIMEOUT_MS} ms.`
        : `${method} ${requestPath} never reached a server. The backend is probably not running.`,
      requestPath,
      cause,
    })
    logEvent('error', 'api.request_failed', {
      method,
      path: requestPath,
      kind: error.kind,
      timed_out: timedOut,
      reason: error.detail,
    })
    throw error
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', forwardAbort)
  }

  if (!received.answered) {
    const error = errorFromResponse(response, received.raw, requestPath)
    logEvent('warn', 'api.request_rejected', {
      method,
      path: requestPath,
      status: response.status,
      kind: error.kind,
      problem_type: error.problem?.type ?? null,
      request_id: error.requestId,
    })
    throw error
  }

  return { response, body: received.body, requestPath, requestId: requestIdFromHeaders(response) }
}
