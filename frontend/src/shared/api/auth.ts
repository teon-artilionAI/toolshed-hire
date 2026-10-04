/**
 * The session routes and the current account.
 *
 * Four calls. Login exchanges an email address and a password for an access
 * token. Refresh exchanges the refresh cookie for a new one. Logout ends the
 * session on the server. `GET /api/me` says whom the access token belongs to.
 *
 * The refresh token never passes through this file. The server sets it as an
 * HttpOnly cookie and the browser sends it back by itself, because every
 * request the client makes includes credentials. I never read it and never try
 * to.
 *
 * Login, refresh and logout switch off the client's renewal rule. A refused
 * login is a wrong password, and a refused refresh is the end of the session.
 * Neither is cured by asking for another refresh.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type { LoginRequest, SessionGrant, SessionUser, UserRole } from './contract'
import { readFlag, readObject, readText } from './read'

const LOGIN_ENDPOINT = '/auth/login'
const REFRESH_ENDPOINT = '/auth/refresh'
const LOGOUT_ENDPOINT = '/auth/logout'
const CURRENT_USER_ENDPOINT = '/me'

/** How the `type` of the problem ends when a sign in is refused. The API sends
 *  the same one for a wrong password, an unknown address and a locked account. */
export const INVALID_CREDENTIALS = 'invalid-credentials'

/** How the `type` ends when the caller has tried too often and must wait. */
export const TOO_MANY_ATTEMPTS = 'too-many-attempts'

/** How the `type` ends when the refresh cookie is absent or no longer good. */
export const SESSION_EXPIRED = 'session-expired'

/** The roles the API uses on the wire. */
const WIRE_ROLES: readonly UserRole[] = ['customer', 'counter', 'admin']

/** The one token type the contract names. */
const BEARER = 'Bearer'

const OWN_ROUTE = { skipSessionRenewal: true } as const

function isWireRole(value: string): value is UserRole {
  return WIRE_ROLES.some((role) => role === value)
}

/**
 * Read the branch code of an account.
 *
 * The API sends null for anyone who is not counter staff. The OpenAPI document
 * also lets the member be left out, so I read a missing one as null. Locking
 * every customer out over that would change nothing for the better.
 */
function readBranchCode(record: Record<string, unknown>, requestPath: string): string | null {
  const value = record.branchCode
  if (value === undefined || value === null) return null
  if (typeof value === 'string') return value
  throw malformedResponse(
    requestPath,
    `Expected field branchCode in the response from ${requestPath} to be text or null, got ` +
      `${typeof value}.`,
  )
}

/**
 * Read an account out of a response body.
 *
 * @throws ApiError of kind `malformed` when a field is missing or the role is
 *   not one the contract knows, which would mean the backend and contract.ts
 *   have drifted apart.
 */
function readSessionUser(value: unknown, requestPath: string): SessionUser {
  const record = readObject(value, requestPath, 'an account object')
  const role = readText(record, 'role', requestPath)
  if (!isWireRole(role)) {
    throw malformedResponse(
      requestPath,
      `The API returned role ${role}, which is not one of ${WIRE_ROLES.join(', ')}. The role ` +
        'mapping in the backend and the UserRole union in contract.ts have drifted apart.',
    )
  }
  return {
    id: readText(record, 'id', requestPath),
    email: readText(record, 'email', requestPath),
    fullName: readText(record, 'fullName', requestPath),
    role,
    branchCode: readBranchCode(record, requestPath),
    emailVerified: readFlag(record, 'emailVerified', requestPath),
    emailDeliverable: readFlag(record, 'emailDeliverable', requestPath),
  }
}

function readSessionGrant(value: unknown, requestPath: string): SessionGrant {
  const record = readObject(value, requestPath, 'a session object')
  const tokenType = readText(record, 'tokenType', requestPath)
  if (tokenType !== BEARER) {
    throw malformedResponse(
      requestPath,
      `The API returned token type ${tokenType} from ${requestPath}, and this client only ` +
        `knows how to send a ${BEARER} token.`,
    )
  }
  const expiresIn = record.expiresIn
  if (typeof expiresIn !== 'number' || !Number.isFinite(expiresIn) || expiresIn <= 0) {
    throw malformedResponse(
      requestPath,
      `Expected field expiresIn in the response from ${requestPath} to be a number of seconds ` +
        'above zero.',
    )
  }
  return {
    accessToken: readText(record, 'accessToken', requestPath),
    tokenType: BEARER,
    expiresIn,
    user: readSessionUser(record.user, requestPath),
  }
}

/**
 * POST /api/auth/login.
 *
 * @throws ApiError with status 401 and a type ending `invalid-credentials` for
 *   every refused sign in, whatever the reason. With status 429 and a type
 *   ending `too-many-attempts` when the caller must wait, and then
 *   `retryAfterSeconds` on the error says for how long.
 */
export function login(credentials: LoginRequest): Promise<SessionGrant> {
  return api.post(LOGIN_ENDPOINT, credentials, readSessionGrant, OWN_ROUTE)
}

/**
 * POST /api/auth/refresh. No body. The refresh cookie is the credential.
 *
 * @throws ApiError with status 401 and a type ending `session-expired` when
 *   there is no session to renew.
 */
export function refreshSession(): Promise<SessionGrant> {
  return api.post(REFRESH_ENDPOINT, undefined, readSessionGrant, OWN_ROUTE)
}

/**
 * POST /api/auth/logout. No body, and always 204 with none.
 *
 * @throws ApiError only when the API could not be reached or answered with
 *   something other than the 204 the contract promises.
 */
export function logout(): Promise<void> {
  return api.post(LOGOUT_ENDPOINT, undefined, () => undefined, OWN_ROUTE)
}

/**
 * GET /api/me. The account the session's access token belongs to.
 *
 * @throws ApiError with status 401 when nobody is signed in and the session
 *   could not be renewed.
 */
export function getCurrentUser(): Promise<SessionUser> {
  return api.get(CURRENT_USER_ENDPOINT, readSessionUser)
}
