/**
 * The typed API client.
 *
 * THE BASE PATH IS RELATIVE, ALWAYS
 * =================================
 * Every request is made against `/api`, never against an absolute origin. That
 * single rule is what keeps the browser on one origin. In production Vercel
 * rewrites `/api/*` to Cloud Run server side, and in development the proxy in
 * vite.config.ts does the same to the local uvicorn process, so a relative path
 * resolves to the page's own origin in both places. Writing
 * `http://localhost:8000` here instead would reintroduce exactly the cross
 * origin condition the architecture exists to avoid: a preflight on every call,
 * and a refresh cookie that `SameSite=Strict` will not send.
 *
 * WHAT THIS FILE IS NOT
 * =====================
 * It is not wired into the twenty four screens. Those still read from
 * fixtures.ts, which is what the prototype is marked on. This client exists so
 * the path from the browser to PostgreSQL is proved rather than assumed, and it
 * is exercised by the connectivity panel at /system. Converting the screens is
 * separate work with its own budget.
 *
 * Failures are typed and never swallowed. See api-problem.ts for `ApiError`.
 */

import type { Role } from './types'
import {
  ApiError,
  asRecord,
  errorFromResponse,
  malformedResponse,
  parseJsonBody,
  requireField,
} from './api-problem'

export type { ApiFailureKind, ProblemDocument } from './api-problem'
export { ApiError, asApiError, isApiError } from './api-problem'

/** The one prefix the API is mounted under. Matches `API_PREFIX` in the backend
 *  router assembly and the rewrite source in vercel.json. All three must agree. */
export const API_BASE_PATH = '/api'

/** How long a request may take before it is abandoned. Long enough for a cold
 *  Cloud Run instance, short enough that a dead backend does not leave a panel
 *  spinning with nothing to say. */
const REQUEST_TIMEOUT_MS = 8000

/** The wire values the backend maps its stored roles onto. */
const WIRE_ROLES: readonly Role[] = ['customer', 'counter', 'admin']

/** The status the health endpoint uses to say a dependency is down while still
 *  reporting which one, so an uptime check need not parse the body to decide. */
const HTTP_SERVICE_UNAVAILABLE = 503

/** The path a call is made against, relative by construction. */
export function apiPath(endpoint: string): string {
  return `${API_BASE_PATH}${endpoint}`
}

/**
 * The absolute URL the browser resolves an API path to.
 *
 * Used by the connectivity panel to show, rather than claim, that the request
 * origin and the page origin are the same one.
 */
export function resolvedApiUrl(endpoint: string): string {
  return new URL(apiPath(endpoint), window.location.href).toString()
}

/** Structured console logging, so a failed call leaves a readable trail with the
 *  method, the path and the reason rather than a bare message. */
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

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  /** Bearer token for a protected endpoint. Omitted on public ones. */
  accessToken?: string
  /**
   * Statuses whose body carries the answer rather than a failure.
   *
   * `/api/health` answers 503 while a dependency is down, and the body of that
   * 503 is the report naming which dependency. Throwing it away and reporting
   * "the request failed" would discard the only useful thing in the response.
   */
  bodyBearingStatuses?: readonly number[]
}

/**
 * Make one request and return its parsed body.
 *
 * @param endpoint Path below the `/api` base, for example `/health`.
 * @param options Method, body and bearer token.
 * @returns The parsed JSON body, or null for an empty response.
 * @throws ApiError on a transport failure, a non 2xx response, or a body that is
 *   not JSON. It never returns null to mean failure.
 */
async function request(endpoint: string, options: RequestOptions = {}): Promise<unknown> {
  const requestPath = apiPath(endpoint)
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.accessToken) headers.Authorization = `Bearer ${options.accessToken}`

  logApiEvent('info', 'api.request_started', { method, path: requestPath })

  let response: Response
  try {
    response = await fetch(requestPath, {
      method,
      headers,
      // Same origin by construction, so cookies would travel under the default
      // policy too. It is stated explicitly because the refresh cookie is the
      // thing the single origin decision exists to protect, and a default that
      // happens to do the right thing is not the same as a decision.
      credentials: 'include',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (cause) {
    const timedOut = cause instanceof DOMException && cause.name === 'TimeoutError'
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
      reason: error.detail,
    })
    throw error
  }

  // Read once as text, then decide. A failed response may carry a problem
  // document, a proxy's own error page or nothing at all, and only one of those
  // is JSON, so parsing before the decision would turn a 502 into a complaint
  // about syntax rather than a report that the API was not reached.
  const raw = await response.text()
  const answered = response.ok || (options.bodyBearingStatuses?.includes(response.status) ?? false)
  if (!answered) {
    const error = errorFromResponse(response, raw, requestPath)
    logApiEvent('warn', 'api.request_rejected', {
      method,
      path: requestPath,
      status: response.status,
      kind: error.kind,
      problem_type: error.problem?.type ?? null,
    })
    throw error
  }

  logApiEvent('info', 'api.request_succeeded', {
    method,
    path: requestPath,
    status: response.status,
  })
  return parseJsonBody(raw, response.status, requestPath)
}

/** What the health endpoint reports about its own dependencies. */
export interface HealthReport {
  status: string
  environment: string
  databaseReachable: boolean
  btreeGistInstalled: boolean
}

/** An account as the API describes it. Matches `UserResponse` on the backend. */
export interface ApiUserAccount {
  id: string
  name: string
  email: string
  role: Role
  /** Counter staff carry a branch. Customers and administrators do not, so null
   *  here is a fact about the role rather than missing data. */
  branchCode: string | null
  active: boolean
}

/** A successful sign in: the token, its lifetime, and whom it belongs to. */
export interface SignInResult {
  accessToken: string
  tokenType: string
  expiresIn: number
  user: ApiUserAccount
}

/**
 * Read an account out of a response body.
 *
 * @throws ApiError of kind `malformed` when a field is missing or the role is
 *   not one the frontend union knows, which would mean the backend mapping and
 *   types.ts have drifted apart.
 */
function parseUser(value: unknown, requestPath: string): ApiUserAccount {
  const record = asRecord(value)
  if (!record) throw malformedResponse(requestPath, `Expected an account object from ${requestPath}.`)
  const role = requireField<string>(record, 'role', 'string', requestPath)
  if (!WIRE_ROLES.includes(role as Role)) {
    throw malformedResponse(
      requestPath,
      `The API returned role ${role}, which is not one of ${WIRE_ROLES.join(', ')}. The role ` +
        'mapping in the backend schemas and the Role union in types.ts have drifted apart.',
    )
  }
  const branchCode = record.branchCode
  return {
    id: requireField<string>(record, 'id', 'string', requestPath),
    name: requireField<string>(record, 'name', 'string', requestPath),
    email: requireField<string>(record, 'email', 'string', requestPath),
    role: role as Role,
    branchCode: typeof branchCode === 'string' ? branchCode : null,
    active: requireField<boolean>(record, 'active', 'boolean', requestPath),
  }
}

/**
 * GET /api/health. Public, and the only endpoint with no role policy.
 *
 * A degraded dependency answers 503 with the report still in the body, and that
 * body is returned rather than thrown, because "the database is unreachable" is
 * the answer to the question this endpoint was asked.
 *
 * @throws ApiError when the API itself could not be reached or answered in a
 *   shape this client does not recognise.
 */
export async function getHealth(): Promise<HealthReport> {
  const path = apiPath('/health')
  const record = asRecord(
    await request('/health', { bodyBearingStatuses: [HTTP_SERVICE_UNAVAILABLE] }),
  )
  if (!record) throw malformedResponse(path, `Expected a health object from ${path}.`)
  return {
    status: requireField<string>(record, 'status', 'string', path),
    environment: requireField<string>(record, 'environment', 'string', path),
    databaseReachable: requireField<boolean>(record, 'databaseReachable', 'boolean', path),
    btreeGistInstalled: requireField<boolean>(record, 'btreeGistInstalled', 'boolean', path),
  }
}

/**
 * POST /api/auth/sign-in.
 *
 * @throws ApiError with status 401 for a wrong password and for an unknown
 *   address alike. The two are answered identically on purpose, so this client
 *   cannot tell them apart either, and neither can anyone using it.
 */
export async function signIn(email: string, password: string): Promise<SignInResult> {
  const path = apiPath('/auth/sign-in')
  const record = asRecord(
    await request('/auth/sign-in', { method: 'POST', body: { email, password } }),
  )
  if (!record) throw malformedResponse(path, `Expected a token object from ${path}.`)
  return {
    accessToken: requireField<string>(record, 'accessToken', 'string', path),
    tokenType: requireField<string>(record, 'tokenType', 'string', path),
    expiresIn: requireField<number>(record, 'expiresIn', 'number', path),
    user: parseUser(record.user, path),
  }
}

/**
 * GET /api/me. Protected, and the endpoint that proves the whole chain: a token
 * from the browser, a verified signature, a row loaded from PostgreSQL, and a
 * role read from that row rather than from the token.
 *
 * @throws ApiError with status 401 when the token is absent, expired or forged.
 */
export async function getCurrentUser(accessToken: string): Promise<ApiUserAccount> {
  return parseUser(await request('/me', { accessToken }), apiPath('/me'))
}
