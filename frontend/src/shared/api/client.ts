/**
 * The typed HTTP client. Every call to the API goes through this file.
 *
 * THE BASE PATH IS RELATIVE, ALWAYS
 * =================================
 * Every request is made against `/api`, never against an absolute origin. That
 * single rule is what keeps the browser on one origin. In production Vercel
 * rewrites `/api/*` to Cloud Run server side, and in development the proxy in
 * vite.config.ts does the same to the local uvicorn process, so a relative path
 * resolves to the page's own origin in both places. Writing
 * `http://localhost:8000` here would bring back the cross origin condition the
 * architecture exists to avoid. Every call would be preflighted, the refresh
 * cookie would not be sent under `SameSite=Strict`, and the Content Security
 * Policy would refuse the request, because it only allows `connect-src 'self'`.
 *
 * WHAT A CALL LOOKS LIKE
 * ======================
 * A caller names the endpoint, hands over a reader that turns the unknown body
 * into the type it wants, and gets that type back or an `ApiError`. The reader
 * is not optional. A body that was never checked is a guess about its shape,
 * and a wrong guess surfaces three screens away as `undefined`.
 *
 * There are four verbs, GET, POST, PUT and PATCH. This system never deletes a
 * record, so there is no DELETE here and none should be added.
 *
 * WHERE THE BEARER TOKEN COMES FROM
 * =================================
 * The client asks a provider function for the token on every request. Nothing
 * is registered yet, so nothing is sent. The session will register its provider
 * through `registerAccessTokenProvider` and will not need to change this file.
 *
 * Failures are typed and never swallowed. See api-problem.ts for `ApiError`.
 */

import {
  ApiError,
  asApiError,
  errorFromResponse,
  parseJsonBody,
  requestIdFromHeaders,
} from '../api-problem'
import { buildQueryString } from './query-string'
import type { QueryShape } from './query-string'

/** The one prefix the API is mounted under. Matches `API_PREFIX` in the backend
 *  router assembly and the rewrite source in vercel.json. All three must agree. */
export const API_BASE_PATH = '/api'

/** How long a request may take before it is abandoned. Long enough for a cold
 *  Cloud Run instance, short enough that a dead backend does not leave a screen
 *  waiting with nothing to say. */
export const REQUEST_TIMEOUT_MS = 8000

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH'

/** Turns the unknown body of a successful response into the type a caller
 *  wants, or throws an `ApiError` of kind `malformed`. */
export type BodyReader<Result> = (body: unknown, requestPath: string) => Result

/** Supplies the bearer token for a request, or null when nobody is signed in. */
export type AccessTokenProvider = () => string | null

export interface RequestOptions<Query> {
  /** Members that are undefined, null or empty are left out of the address. */
  query?: Query
  /** A token for this one call. It wins over the registered provider. */
  accessToken?: string
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

let accessTokenProvider: AccessTokenProvider | null = null

/**
 * Tell the client where to get the bearer token from.
 *
 * @param provider Called once per request. Pass null to go back to sending no
 *   token, which is what signing out needs.
 */
export function registerAccessTokenProvider(provider: AccessTokenProvider | null): void {
  accessTokenProvider = provider
}

/** The path a call is made against, relative by construction. */
export function apiPath(endpoint: string): string {
  return `${API_BASE_PATH}${endpoint}`
}

/**
 * The absolute URL the browser resolves an API path to.
 *
 * The connectivity panel uses it to show that the request origin and the page
 * origin are the same one.
 */
export function resolvedApiUrl(endpoint: string): string {
  return new URL(apiPath(endpoint), window.location.href).toString()
}

/** Structured console logging, so a failed call leaves a readable trail with the
 *  method, the path and the reason and not a bare message. */
function logApiEvent(
  level: 'info' | 'warn' | 'error',
  event: string,
  context: Record<string, unknown>,
): void {
  const entry = { event, ...context }
  if (level === 'error') console.error(event, entry)
  else if (level === 'warn') console.warn(event, entry)
  else console.info(event, entry)
}

/** Give an error the request id of the response it came from, if it has none. */
function withRequestId(error: ApiError, requestId: string | null): ApiError {
  if (error.requestId !== null || requestId === null) return error
  return new ApiError({
    kind: error.kind,
    status: error.status,
    title: error.title,
    detail: error.detail,
    requestPath: error.requestPath,
    problem: error.problem,
    requestId,
    cause: error.cause,
  })
}

/**
 * Make one request and return its body, read into the caller's type.
 *
 * @throws ApiError on a transport failure, a timeout, a non 2xx response, a
 *   body that is not JSON, or a body the reader refuses. The one exception is a
 *   request the caller abandoned through `signal`. That rethrows the abort
 *   untouched, because it is not a failure and must not be shown as one.
 */
async function request<Result, Query extends QueryShape<Query>>(
  method: HttpMethod,
  endpoint: string,
  read: BodyReader<Result>,
  options: RequestOptions<Query> & { body?: unknown },
): Promise<Result> {
  const requestPath = apiPath(endpoint)
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  const token = options.accessToken ?? accessTokenProvider?.() ?? null
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

  logApiEvent('info', 'api.request_started', { method, path: requestPath })

  let response: Response
  let raw: string
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
    // Read once as text, then decide. A failed response may carry a problem
    // document, a proxy's own error page or nothing at all, and only one of
    // those is JSON. The read sits inside the timeout because a body can stall
    // as easily as a header can.
    raw = await response.text()
  } catch (cause) {
    if (!timedOut && options.signal?.aborted) {
      logApiEvent('info', 'api.request_cancelled', { method, path: requestPath })
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
    logApiEvent('error', 'api.request_failed', {
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

  const requestId = requestIdFromHeaders(response)
  const answered = response.ok || (options.bodyBearingStatuses?.includes(response.status) ?? false)
  if (!answered) {
    const error = errorFromResponse(response, raw, requestPath)
    logApiEvent('warn', 'api.request_rejected', {
      method,
      path: requestPath,
      status: response.status,
      kind: error.kind,
      problem_type: error.problem?.type ?? null,
      request_id: error.requestId,
    })
    throw error
  }

  try {
    const result = read(parseJsonBody(raw, response.status, requestPath, requestId), requestPath)
    logApiEvent('info', 'api.request_succeeded', {
      method,
      path: requestPath,
      status: response.status,
      request_id: requestId,
    })
    return result
  } catch (cause) {
    const error = withRequestId(asApiError(cause, requestPath), requestId)
    logApiEvent('error', 'api.response_unreadable', {
      method,
      path: requestPath,
      status: response.status,
      kind: error.kind,
      reason: error.detail,
      request_id: requestId,
    })
    throw error
  }
}

/**
 * The four verbs.
 *
 * Each takes the endpoint below `/api`, for example `/catalogue/models`, and a
 * reader for the body. POST, PUT and PATCH also take the JSON body to send.
 */
export const api = {
  get<Result, Query extends QueryShape<Query> = QueryShape<unknown>>(
    endpoint: string,
    read: BodyReader<Result>,
    options: RequestOptions<Query> = {},
  ): Promise<Result> {
    return request('GET', endpoint, read, options)
  },
  post<Result, Query extends QueryShape<Query> = QueryShape<unknown>>(
    endpoint: string,
    body: unknown,
    read: BodyReader<Result>,
    options: RequestOptions<Query> = {},
  ): Promise<Result> {
    return request('POST', endpoint, read, { ...options, body })
  },
  put<Result, Query extends QueryShape<Query> = QueryShape<unknown>>(
    endpoint: string,
    body: unknown,
    read: BodyReader<Result>,
    options: RequestOptions<Query> = {},
  ): Promise<Result> {
    return request('PUT', endpoint, read, { ...options, body })
  },
  patch<Result, Query extends QueryShape<Query> = QueryShape<unknown>>(
    endpoint: string,
    body: unknown,
    read: BodyReader<Result>,
    options: RequestOptions<Query> = {},
  ): Promise<Result> {
    return request('PATCH', endpoint, read, { ...options, body })
  },
}
