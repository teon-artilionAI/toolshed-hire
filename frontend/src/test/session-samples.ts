/**
 * Accounts and session answers for tests, shaped the way the API sends them.
 *
 * One account for each role, the body login and refresh answer with, and the
 * refusals the session routes send. The route tables at the bottom are the
 * three starting points almost every test needs. Nobody is signed in, somebody
 * is, or the answer has not arrived yet.
 */

import { isApiError } from '../shared/api-problem'
import type { ApiError } from '../shared/api-problem'
import type { SessionGrant, SessionUser } from '../shared/api/contract'
import { jsonResponse, neverAnswers, noContentResponse, problemResponse } from './api-mock'
import type { RouteHandler, RouteTable, SeenRequest } from './api-mock'
import { BRANCHES } from './catalogue-samples'

export const LOGIN_ROUTE = 'POST /api/auth/login'
export const REFRESH_ROUTE = 'POST /api/auth/refresh'
export const LOGOUT_ROUTE = 'POST /api/auth/logout'
export const ME_ROUTE = 'GET /api/me'
export const BRANCHES_ROUTE = 'GET /api/branches'

export const CUSTOMER: SessionUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000001',
  email: 'w.adonis@buildright.co.za',
  fullName: 'Wesley Adonis',
  role: 'customer',
  branchCode: null,
  emailVerified: true,
}

export const COUNTER_STAFF: SessionUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000002',
  email: 'thabo@toolshedhire.co.za',
  fullName: 'Thabo Ncube',
  role: 'counter',
  branchCode: 'BLV',
  emailVerified: true,
}

export const ADMIN: SessionUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000005',
  email: 'marius@toolshedhire.co.za',
  fullName: 'Marius Pretorius',
  role: 'admin',
  branchCode: null,
  emailVerified: true,
}

/** The token the samples issue, unless a test names another. It is long and
 *  odd on purpose, so a test can search for it and know a match is no accident. */
export const ACCESS_TOKEN = 'test-access-token-7f3a9c1e5b2d'

const ACCESS_TOKEN_SECONDS = 900

/** What login and refresh answer with for one account. */
export function grantFor(user: SessionUser, accessToken = ACCESS_TOKEN): SessionGrant {
  return { accessToken, tokenType: 'Bearer', expiresIn: ACCESS_TOKEN_SECONDS, user }
}

/** The 401 a refresh answers with when there is no session to renew. */
export function sessionExpired(): Response {
  return problemResponse(401, { slug: 'session-expired', detail: 'Sign in again.' })
}

/** The 401 a protected route answers with for a token that is no longer good. */
export function tokenRefused(): Response {
  return problemResponse(401, { slug: 'authentication-failure', detail: 'The token is not valid.' })
}

/** The 401 every refused sign in gets, whatever the reason. */
export function invalidCredentials(): Response {
  return problemResponse(401, { slug: 'invalid-credentials', detail: 'Sign in refused.' })
}

/** The 429 a sign in gets after too many attempts, with the wait in seconds. */
export function tooManyAttempts(retryAfterSeconds: number): Response {
  return problemResponse(429, {
    slug: 'too-many-attempts',
    detail: 'Too many sign in attempts.',
    headers: { 'Retry-After': String(retryAfterSeconds) },
  })
}

/** The bearer token a request carried, or null when it carried none. */
export function bearerOf(request: SeenRequest): string | null {
  const header = request.headers.get('Authorization')
  return header === null ? null : header.replace(/^Bearer /, '')
}

/** `GET /api/me` that accepts one token and refuses every other. */
export function meAccepting(token: string, account: SessionUser = CUSTOMER): RouteHandler {
  return (request) => (bearerOf(request) === token ? jsonResponse(account) : tokenRefused())
}

/** Run a call that must fail and hand back the ApiError it threw. */
export async function failureOf(call: Promise<unknown>): Promise<ApiError> {
  try {
    await call
  } catch (thrown) {
    if (isApiError(thrown)) return thrown
    throw thrown
  }
  throw new Error('Expected the call to throw an ApiError, and it returned instead.')
}

/** Start-up finds no session. */
export const SIGNED_OUT: RouteTable = {
  [REFRESH_ROUTE]: () => sessionExpired(),
}

/** Start-up has not heard back. */
export const STILL_CHECKING: RouteTable = {
  [REFRESH_ROUTE]: () => neverAnswers(),
}

/**
 * Start-up finds a session for this account.
 *
 * Sign out answers 204, and the branch list is there because the counter
 * layout asks for it to name the branch on the account.
 */
export function signedInAs(user: SessionUser): RouteTable {
  return {
    [REFRESH_ROUTE]: () => jsonResponse(grantFor(user)),
    [LOGOUT_ROUTE]: () => noContentResponse(),
    [BRANCHES_ROUTE]: () => jsonResponse(BRANCHES),
  }
}
