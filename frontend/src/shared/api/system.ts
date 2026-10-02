/**
 * The health, sign in and current account endpoints.
 *
 * These are the three calls the connectivity panel at /system makes. They were
 * the first endpoints the client ever reached, and they stay together here so
 * the panel has one module to import.
 */

import { asRecord, malformedResponse, requireField } from '../api-problem'
import { api } from './client'
import type { ApiUserAccount, HealthReport, SignInResult, UserRole } from './contract'

/** The wire values the backend maps its stored roles onto. */
const WIRE_ROLES: readonly UserRole[] = ['customer', 'counter', 'admin']

/** The status the health endpoint uses to say a dependency is down while still
 *  reporting which one, so an uptime check need not parse the body to decide. */
const HTTP_SERVICE_UNAVAILABLE = 503

function isWireRole(value: string): value is UserRole {
  return WIRE_ROLES.some((role) => role === value)
}

/**
 * Read an account out of a response body.
 *
 * @throws ApiError of kind `malformed` when a field is missing or the role is
 *   not one the contract knows, which would mean the backend mapping and
 *   contract.ts have drifted apart.
 */
function readUser(value: unknown, requestPath: string): ApiUserAccount {
  const record = asRecord(value)
  if (!record) throw malformedResponse(requestPath, `Expected an account object from ${requestPath}.`)
  const role = requireField<string>(record, 'role', 'string', requestPath)
  if (!isWireRole(role)) {
    throw malformedResponse(
      requestPath,
      `The API returned role ${role}, which is not one of ${WIRE_ROLES.join(', ')}. The role ` +
        'mapping in the backend schemas and the UserRole union in contract.ts have drifted apart.',
    )
  }
  const branchCode = record.branchCode
  return {
    id: requireField<string>(record, 'id', 'string', requestPath),
    name: requireField<string>(record, 'name', 'string', requestPath),
    email: requireField<string>(record, 'email', 'string', requestPath),
    role,
    branchCode: typeof branchCode === 'string' ? branchCode : null,
    active: requireField<boolean>(record, 'active', 'boolean', requestPath),
  }
}

function readHealth(value: unknown, requestPath: string): HealthReport {
  const record = asRecord(value)
  if (!record) throw malformedResponse(requestPath, `Expected a health object from ${requestPath}.`)
  return {
    status: requireField<string>(record, 'status', 'string', requestPath),
    environment: requireField<string>(record, 'environment', 'string', requestPath),
    databaseReachable: requireField<boolean>(record, 'databaseReachable', 'boolean', requestPath),
    btreeGistInstalled: requireField<boolean>(record, 'btreeGistInstalled', 'boolean', requestPath),
    revision: requireField<string>(record, 'revision', 'string', requestPath),
  }
}

function readSignIn(value: unknown, requestPath: string): SignInResult {
  const record = asRecord(value)
  if (!record) throw malformedResponse(requestPath, `Expected a token object from ${requestPath}.`)
  return {
    accessToken: requireField<string>(record, 'accessToken', 'string', requestPath),
    tokenType: requireField<string>(record, 'tokenType', 'string', requestPath),
    expiresIn: requireField<number>(record, 'expiresIn', 'number', requestPath),
    user: readUser(record.user, requestPath),
  }
}

/**
 * GET /api/health. Public, and the only endpoint with no role policy.
 *
 * A degraded dependency answers 503 with the report still in the body, and that
 * body is returned and not thrown, because "the database is unreachable" is the
 * answer to the question this endpoint was asked.
 *
 * @throws ApiError when the API itself could not be reached or answered in a
 *   shape this client does not recognise.
 */
export function getHealth(): Promise<HealthReport> {
  return api.get('/health', readHealth, { bodyBearingStatuses: [HTTP_SERVICE_UNAVAILABLE] })
}

/**
 * POST /api/auth/sign-in.
 *
 * @throws ApiError with status 401 for a wrong password and for an unknown
 *   address alike. The two are answered identically on purpose, so this client
 *   cannot tell them apart either, and neither can anyone using it.
 */
export function signIn(email: string, password: string): Promise<SignInResult> {
  return api.post('/auth/sign-in', { email, password }, readSignIn)
}

/**
 * GET /api/me. Protected, and the endpoint that proves the whole chain. A token
 * from the browser, a verified signature, a row loaded from PostgreSQL, and a
 * role read from that row and not from the token.
 *
 * @param accessToken The token to present. The connectivity panel signs in by
 *   itself, outside the session, so it passes its own token here.
 * @throws ApiError with status 401 when the token is absent, expired or forged.
 */
export function getCurrentUser(accessToken: string): Promise<ApiUserAccount> {
  return api.get('/me', readUser, { accessToken })
}
