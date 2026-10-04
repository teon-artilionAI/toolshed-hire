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
 * record, so there is no DELETE here and none should be added. A GET can also
 * fetch a file, such as a CSV report, with `getFile`. That goes out the same
 * way, with the same token and the same renewal, and comes back as the bytes
 * and the name the server gave the file.
 *
 * The request itself goes out in transport.ts, which is the one file that
 * calls `fetch`. This file decides what a good answer means.
 *
 * WHERE THE BEARER TOKEN COMES FROM
 * =================================
 * The client asks session-seam.ts for the token on every request. The session
 * registers itself there, so this file never learns how a session is kept.
 *
 * WHAT HAPPENS ON A 401
 * =====================
 * A request refused for want of a good token renews the session once and is
 * repeated once. Requests refused together share one renewal. The rule is
 * `withSessionRenewal` in session-seam.ts. The session's own routes switch it
 * off, because asking for a renewal from inside a renewal would never end.
 *
 * Failures are typed and never swallowed. See api-problem.ts for `ApiError`.
 */

import { ApiError, asApiError, malformedResponse, parseJsonBody } from '../api-problem'
import { CONTENT_DISPOSITION_HEADER, fileNameFromDisposition } from './content-disposition'
import { logEvent } from './log'
import type { QueryShape } from './query-string'
import { withSessionRenewal } from './session-seam'
import { apiPath, exchange } from './transport'
import type { Expectation, HttpMethod, RequestOptions } from './transport'

export { registerAccessTokenProvider } from './session-seam'
export type { AccessTokenProvider } from './session-seam'
export { API_BASE_PATH, REQUEST_TIMEOUT_MS, apiPath } from './transport'
export type { RequestOptions } from './transport'

/** Turns the unknown body of a successful response into the type a caller
 *  wants, or throws an `ApiError` of kind `malformed`. */
export type BodyReader<Result> = (body: unknown, requestPath: string) => Result

/** A file the API sent, and the name the server gave it. */
export interface ApiFile {
  fileName: string
  content: Blob
}

/** Every JSON call accepts JSON and takes the body as text to parse it. */
const JSON_ANSWER: Expectation<string> = {
  accept: 'application/json',
  take: (response) => response.text(),
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
    retryAfterSeconds: error.retryAfterSeconds,
    cause: error.cause,
  })
}

/**
 * Make one request and return its body, read into the caller's type.
 *
 * @param token The bearer token to send, or null to send none.
 * @throws ApiError on a transport failure, a timeout, a non 2xx response, a
 *   body that is not JSON, or a body the reader refuses. A request the caller
 *   abandoned rethrows the abort untouched.
 */
async function send<Result, Query extends QueryShape<Query>>(
  method: HttpMethod,
  endpoint: string,
  read: BodyReader<Result>,
  options: RequestOptions<Query> & { body?: unknown },
  token: string | null,
): Promise<Result> {
  const { response, body, requestPath, requestId } = await exchange(method, endpoint, JSON_ANSWER, options, token)
  try {
    const result = read(parseJsonBody(body, response.status, requestPath, requestId), requestPath)
    logEvent('info', 'api.request_succeeded', {
      method,
      path: requestPath,
      status: response.status,
      request_id: requestId,
    })
    return result
  } catch (cause) {
    const error = withRequestId(asApiError(cause, requestPath), requestId)
    logEvent('error', 'api.response_unreadable', {
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
 * Fetch one file and the name the server gave it.
 *
 * @param accept The media types the call accepts, for example `text/csv`.
 * @throws ApiError as `send` does, and of kind `malformed` when the answer
 *   does not name its file in a `Content-Disposition` header.
 */
async function sendForFile<Query extends QueryShape<Query>>(
  endpoint: string,
  accept: string,
  options: RequestOptions<Query>,
  token: string | null,
): Promise<ApiFile> {
  const { response, body, requestPath, requestId } = await exchange(
    'GET',
    endpoint,
    { accept, take: (answer) => answer.blob() },
    options,
    token,
  )
  const fileName = fileNameFromDisposition(response.headers.get(CONTENT_DISPOSITION_HEADER))
  if (fileName === null) {
    const error = malformedResponse(
      requestPath,
      `Expected ${requestPath} to name its file in a ${CONTENT_DISPOSITION_HEADER} header, and it did not.`,
      requestId,
    )
    logEvent('error', 'api.response_unreadable', {
      method: 'GET',
      path: requestPath,
      status: response.status,
      kind: error.kind,
      reason: error.detail,
      request_id: requestId,
    })
    throw error
  }
  logEvent('info', 'api.request_succeeded', {
    method: 'GET',
    path: requestPath,
    status: response.status,
    request_id: requestId,
    bytes: body.size,
  })
  return { fileName, content: body }
}

/** Make a request with the session's token, renewing the session once and
 *  repeating the request once when it is refused for want of a good token. */
function withToken<Result>(
  method: HttpMethod,
  endpoint: string,
  skipSessionRenewal: boolean | undefined,
  attempt: (token: string | null) => Promise<Result>,
): Promise<Result> {
  return withSessionRenewal(attempt, { renew: !skipSessionRenewal, method, path: apiPath(endpoint) })
}

function request<Result, Query extends QueryShape<Query>>(
  method: HttpMethod,
  endpoint: string,
  read: BodyReader<Result>,
  options: RequestOptions<Query> & { body?: unknown },
): Promise<Result> {
  return withToken(method, endpoint, options.skipSessionRenewal, (token) =>
    send(method, endpoint, read, options, token),
  )
}

/**
 * The four verbs, and the GET of a file.
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
  /** A GET whose answer is a file. The bytes are kept exactly as they came. */
  getFile<Query extends QueryShape<Query> = QueryShape<unknown>>(
    endpoint: string,
    accept: string,
    options: RequestOptions<Query> = {},
  ): Promise<ApiFile> {
    return withToken('GET', endpoint, options.skipSessionRenewal, (token) =>
      sendForFile(endpoint, accept, options, token),
    )
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
