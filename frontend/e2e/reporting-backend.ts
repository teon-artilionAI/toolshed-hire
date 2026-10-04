/**
 * Whether the real backend has the reporting routes.
 *
 * The reporting spec signs the owner in, reads the dashboard and the report,
 * and downloads the CSV. A backend can have every earlier route without
 * these, so the spec asks about the dashboard, the report and the CSV by
 * name, after the session routes in backend.ts. When one is not there the
 * spec skips itself and the run still passes.
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

/** The three reporting routes. The period does not have to hold anything. A
 *  route that is there refuses a request with no token before it looks. */
const REPORTING_PROBE_PATHS: readonly string[] = [
  '/api/admin/dashboard',
  '/api/admin/reports/utilisation?from=2026-09-01&to=2026-10-01',
  '/api/admin/reports/utilisation.csv?from=2026-09-01&to=2026-10-01',
]

/** The reason shown beside a skipped reporting spec in the report. */
export const REPORTING_ROUTES_NEEDED =
  `This needs the reporting routes on the real backend, and one of ${REPORTING_PROBE_PATHS.join(', ')} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that has the ' +
  "owner's dashboard, the utilisation and gross contribution report and its CSV."

/**
 * Ask whether the backend has the reporting routes.
 *
 * @returns True only when the session routes are there and all three
 *   reporting routes answered for themselves. An absent backend is a false and
 *   not a throw.
 */
export async function reportingRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  for (const path of REPORTING_PROBE_PATHS) {
    const status = (await request.get(path, { timeout: HEALTH_TIMEOUT_MS })).status()
    if (!ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM) continue
    if (BACKEND_IS_REQUIRED) {
      throw new Error(
        `${REQUIRE_BACKEND_VARIABLE} is set, so the reporting routes have to be there, and ` +
          `GET ${path} answered ${status}. A skipped spec would hide that.`,
      )
    }
    return false
  }
  return true
}
