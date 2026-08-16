/**
 * The failure half of the API client: RFC 9457 problem documents, the typed
 * error every call throws, and the narrowing helpers that read an unknown body
 * without lying about its shape.
 *
 * It lives beside api.ts rather than inside it so that neither file grows past
 * the point where it can be read in one sitting. api.ts owns the requests and
 * the endpoints. This file owns what happens when one of them does not work.
 *
 * Nothing here returns null to signal a failure. Every path that cannot produce
 * the requested value throws `ApiError`, carrying the status where there was
 * one, so a caller can tell a 409 from a 500 and answer each differently.
 */

const PROBLEM_MEDIA_TYPE = 'application/problem+json'
const HTTP_NO_CONTENT = 204
/** How much of an unparseable body to quote back in the error message. */
const BODY_EXCERPT_LENGTH = 120
/** Statuses an edge returns on the API's behalf when it cannot reach it. */
const GATEWAY_STATUSES: readonly number[] = [502, 503, 504]

/** An RFC 9457 problem document, as the backend's `ProblemDetail` emits it. */
export interface ProblemDocument {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
  errors?: Record<string, unknown>
}

/**
 * Why a call failed.
 *
 * The five are kept apart because they need different words in front of a
 * person. `transport` means the request never reached a server at all.
 * `gateway` means the proxy or rewrite in front of the API answered to say it
 * could not reach the API, which in development almost always means the backend
 * is not running. `problem` means the API answered and said no, in the
 * documented format. `malformed` means something answered but not in the shape
 * the contract promises, which is a defect rather than a refusal. `unexpected`
 * is the fault nobody planned for, kept as its own kind so that wrapping one is
 * never mistaken for a diagnosis.
 */
export type ApiFailureKind = 'transport' | 'gateway' | 'problem' | 'malformed' | 'unexpected'

export interface ApiErrorInput {
  kind: ApiFailureKind
  /** The HTTP status, or null when no response was received at all. */
  status: number | null
  title: string
  detail: string
  requestPath: string
  problem?: ProblemDocument | null
  cause?: unknown
}

/**
 * Every failure this client can produce.
 *
 * `status` is the discriminator a caller reaches for first: 409 is a booking
 * somebody else won, 401 is a credential problem, 500 is a fault. `title` and
 * `detail` come straight from the problem document when there was one, so the
 * sentence shown to a person is the sentence the server chose.
 */
export class ApiError extends Error {
  readonly kind: ApiFailureKind
  readonly status: number | null
  readonly title: string
  readonly detail: string
  readonly requestPath: string
  readonly problem: ProblemDocument | null

  constructor(input: ApiErrorInput) {
    super(`${input.title}: ${input.detail}`, { cause: input.cause })
    this.name = 'ApiError'
    this.kind = input.kind
    this.status = input.status
    this.title = input.title
    this.detail = input.detail
    this.requestPath = input.requestPath
    this.problem = input.problem ?? null
  }

  /** True when the API itself was never reached, whether because nothing
   *  answered or because the proxy in front of it said it could not get there.
   *  Both mean the same thing to a reader: start the backend. */
  get isBackendUnreachable(): boolean {
    return this.kind === 'transport' || this.kind === 'gateway'
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

/**
 * Present any thrown value as an ApiError so a caller has one type to render.
 *
 * The original is kept as `cause` and its message is carried through verbatim.
 * Nothing is discarded and nothing is guessed at: a value that was not an
 * ApiError is reported as `unexpected`, which is the honest label for it.
 */
export function asApiError(cause: unknown, requestPath: string): ApiError {
  if (isApiError(cause)) return cause
  return new ApiError({
    kind: 'unexpected',
    status: null,
    title: 'Something failed that was not an API response',
    detail:
      cause instanceof Error
        ? `${cause.name} while calling ${requestPath}: ${cause.message}`
        : `A non error value was thrown while calling ${requestPath}: ${String(cause)}`,
    requestPath,
    cause,
  })
}

/** Narrow an unknown value to a plain object, or null if it is not one. */
export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** Build a malformed response error naming the endpoint and what was expected. */
export function malformedResponse(requestPath: string, detail: string): ApiError {
  return new ApiError({
    kind: 'malformed',
    status: null,
    title: 'The API answered in an unexpected shape',
    detail,
    requestPath,
  })
}

/**
 * Read a required field, or throw naming the field, its expected type and the
 * endpoint that should have sent it.
 *
 * @throws ApiError of kind `malformed` when the field is absent or wrongly typed.
 */
export function requireField<T>(
  source: Record<string, unknown>,
  key: string,
  expected: 'string' | 'boolean' | 'number',
  requestPath: string,
): T {
  const value = source[key]
  if (typeof value !== expected) {
    throw malformedResponse(
      requestPath,
      `Expected field ${key} of type ${expected} in the response from ${requestPath}, got ` +
        `${value === undefined ? 'nothing' : typeof value}.`,
    )
  }
  return value as T
}

/** Try to read a body as JSON without deciding anything about a failure. */
function tryParse(raw: string): unknown {
  if (!raw) return null
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return undefined
  }
}

/**
 * Read a successful response body as JSON, or explain what arrived instead.
 *
 * The HTML case is called out by name because it is the one that will actually
 * happen: a dev server with no proxy configured answers `/api/health` with the
 * single page application, which parses as nothing and would otherwise surface
 * as an unhelpful syntax error somewhere far from the cause.
 *
 * @throws ApiError of kind `malformed` when the body is not JSON.
 */
export function parseJsonBody(raw: string, status: number, requestPath: string): unknown {
  if (status === HTTP_NO_CONTENT) return null
  const parsed = tryParse(raw)
  if (parsed !== undefined) return parsed
  const excerpt = raw.slice(0, BODY_EXCERPT_LENGTH)
  throw new ApiError({
    kind: 'malformed',
    status,
    title: 'The API answered with something that is not JSON',
    detail: excerpt.trimStart().startsWith('<')
      ? `${requestPath} returned HTML, which is what the dev server returns when it serves ` +
        'the single page application instead of proxying the call. Check the server.proxy ' +
        `block in vite.config.ts. The body began: ${excerpt}`
      : `${requestPath} returned a body that could not be parsed as JSON: ${excerpt}`,
    requestPath,
  })
}

/**
 * Turn a failed response into an ApiError.
 *
 * Three cases, in the order they are tested. A problem document is used as it
 * stands, because the server chose those words. A 502, 503 or 504 carrying no
 * JSON object at all is the edge in front of the API answering on its behalf,
 * which means the API was never reached: the Vite proxy in development, the
 * Vercel rewrite in production. Anything else is reported by its status, and
 * says plainly that a problem document was expected and did not arrive.
 *
 * The gateway test insists on the absence of a JSON object on purpose.
 * `/api/health` answers 503 with a health report naming the dependency that is
 * down, and that is the API speaking rather than an edge failing to reach it.
 */
export function errorFromResponse(
  response: Response,
  raw: string,
  requestPath: string,
): ApiError {
  const body = tryParse(raw)
  const record = asRecord(body)
  const isProblem = response.headers.get('content-type')?.startsWith(PROBLEM_MEDIA_TYPE) ?? false
  if (record && isProblem && typeof record.detail === 'string') {
    const problem: ProblemDocument = {
      type: typeof record.type === 'string' ? record.type : 'about:blank',
      title: typeof record.title === 'string' ? record.title : response.statusText,
      status: typeof record.status === 'number' ? record.status : response.status,
      detail: record.detail,
      instance: typeof record.instance === 'string' ? record.instance : undefined,
      errors: asRecord(record.errors) ?? undefined,
    }
    return new ApiError({
      kind: 'problem',
      status: response.status,
      title: problem.title,
      detail: problem.detail,
      requestPath,
      problem,
    })
  }
  if (record === null && GATEWAY_STATUSES.includes(response.status)) {
    return new ApiError({
      kind: 'gateway',
      status: response.status,
      title: 'The API could not be reached',
      detail:
        `${requestPath} answered ${response.status} with no JSON body, which is the proxy in ` +
        'front of the API speaking rather than the API itself. The Vite dev server returns an ' +
        'empty 502 like this when nothing is listening on the port it forwards to.',
      requestPath,
    })
  }
  return new ApiError({
    kind: 'problem',
    status: response.status,
    title: response.statusText || `HTTP ${response.status}`,
    detail:
      `${requestPath} answered ${response.status} without a problem document. Every error ` +
      'from this API is meant to arrive as application/problem+json.',
    requestPath,
  })
}
