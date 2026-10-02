/**
 * The health endpoint.
 *
 * It is the one route with no role policy, and the connectivity panel at
 * /system calls it to show that the API and the database behind it answer.
 * The session routes and `GET /api/me` are in auth.ts.
 */

import { asRecord, malformedResponse, requireField } from '../api-problem'
import { api } from './client'
import type { HealthReport } from './contract'

/** The status the health endpoint uses to say a dependency is down while still
 *  reporting which one, so an uptime check need not parse the body to decide. */
const HTTP_SERVICE_UNAVAILABLE = 503

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
