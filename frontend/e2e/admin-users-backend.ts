/**
 * Whether the real backend has the staff account and customer hold routes.
 *
 * The user management spec signs the owner in, opens a staff account of its
 * own, deactivates and reactivates it, and opens the customer holds. A backend
 * can have every earlier route without these, so the spec asks about both
 * lists by name, after the session routes in backend.ts. The writes were built
 * with them. When one is not there the spec skips itself and the run still
 * passes.
 */

import type { APIRequestContext } from '@playwright/test'
import {
  BACKEND_IS_REQUIRED,
  HEALTH_TIMEOUT_MS,
  REQUIRE_BACKEND_VARIABLE,
  ROUTE_ABSENT_STATUSES,
  SERVER_FAILURE_FROM,
  sessionRoutesArePresent,
} from './backend.ts'

/** The staff accounts and the customer holds. A route that is there refuses a
 *  request with no token before it looks. */
const USER_PROBE_PATHS: readonly string[] = ['/api/admin/users', '/api/admin/customers']

/** The reason shown beside a skipped user management spec in the report. */
export const USER_ROUTES_NEEDED =
  `This needs the user management routes on the real backend, and one of ${USER_PROBE_PATHS.join(' and ')} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that can list, open, ' +
  'change, deactivate and reactivate staff accounts and list and move customer holds.'

/**
 * Ask whether the backend has the user management routes.
 *
 * @returns True only when the session routes are there and both lists
 *   answered for themselves. An absent backend is a false and not a throw.
 */
export async function userRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  for (const path of USER_PROBE_PATHS) {
    const status = (await request.get(path, { timeout: HEALTH_TIMEOUT_MS })).status()
    if (!ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM) continue
    if (BACKEND_IS_REQUIRED) {
      throw new Error(
        `${REQUIRE_BACKEND_VARIABLE} is set, so the user management routes have to be there, and ` +
          `GET ${path} answered ${status}. A skipped spec would hide that.`,
      )
    }
    return false
  }
  return true
}
