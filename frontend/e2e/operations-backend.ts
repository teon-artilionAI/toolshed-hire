/**
 * Whether the real backend has the admin operations routes.
 *
 * The admin operations spec checks a hire out and takes it back through the
 * counter, then has the owner read the audit trail and the notification log and
 * reverse the hire charge. A backend can have the returns routes without these,
 * so the spec asks about the trail and the log by name, after the returns
 * routes in backend.ts. The writes were built with them. When one is not
 * there the spec skips itself and the run still passes.
 */

import type { APIRequestContext } from '@playwright/test'
import {
  BACKEND_IS_REQUIRED,
  HEALTH_TIMEOUT_MS,
  REQUIRE_BACKEND_VARIABLE,
  ROUTE_ABSENT_STATUSES,
  SERVER_FAILURE_FROM,
  returnRoutesArePresent,
} from './backend.ts'

/** The trail and the log. A route that is there refuses a request with no
 *  token before it looks. */
const OPERATIONS_PROBE_PATHS: readonly string[] = ['/api/admin/audit-events', '/api/admin/notifications']

/** The reason shown beside a skipped admin operations spec in the report. */
export const OPERATIONS_ROUTES_NEEDED =
  `This needs the admin operations routes on the real backend, and one of ${OPERATIONS_PROBE_PATHS.join(' and ')} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that has the audit ' +
  'trail, the notification log and the charge corrections.'

/**
 * Ask whether the backend has the admin operations routes, on top of the
 * returns routes the spec checks a hire out and takes it back through.
 *
 * @returns True only when the returns routes are there and both of these
 *   answered for themselves. An absent backend is a false and not a throw.
 */
export async function operationsRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await returnRoutesArePresent(request))) return false
  for (const path of OPERATIONS_PROBE_PATHS) {
    const status = (await request.get(path, { timeout: HEALTH_TIMEOUT_MS })).status()
    if (!ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM) continue
    if (BACKEND_IS_REQUIRED) {
      throw new Error(
        `${REQUIRE_BACKEND_VARIABLE} is set, so the admin operations routes have to be there, and ` +
          `GET ${path} answered ${status}. A skipped spec would hide that.`,
      )
    }
    return false
  }
  return true
}
