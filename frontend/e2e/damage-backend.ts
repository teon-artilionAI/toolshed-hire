/**
 * Whether the real backend has the damage and quarantine routes.
 *
 * The damage journey of the counter spec takes a unit back worse than it went
 * out, files a damage report against it and has the owner resolve it. A
 * backend can have the returns and settlement routes without these, so the
 * journey asks an eighth question, after the seventh in backend.ts, about the
 * list of damage reports by name. When it is not there the journey skips
 * itself and the run still passes.
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

/** The list of damage reports. If it is there, the writes were built with it.
 *  A route that is there refuses a request with no token before it looks. */
const DAMAGE_PROBE_PATH = '/api/damage-reports?assetTag=probe'

/** The reason shown beside a skipped damage journey in the report. */
export const DAMAGE_ROUTES_NEEDED =
  `This needs the damage and quarantine routes on the real backend, and GET ${DAMAGE_PROBE_PATH} answered ` +
  'as a route that is not there. Run the browser tests again against a backend that can file a damage ' +
  'report, list the reports of a unit and resolve one.'

/**
 * Ask whether the backend has the damage routes, on top of the returns routes
 * the journey takes a unit back through.
 *
 * @returns True only when the returns routes are there and the damage list
 *   answered for itself. An absent backend is a false and not a throw.
 */
export async function damageRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await returnRoutesArePresent(request))) return false
  const status = (await request.get(DAMAGE_PROBE_PATH, { timeout: HEALTH_TIMEOUT_MS })).status()
  const present = !ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM
  if (!present && BACKEND_IS_REQUIRED) {
    throw new Error(
      `${REQUIRE_BACKEND_VARIABLE} is set, so the damage and quarantine routes have to be there, and ` +
        `GET ${DAMAGE_PROBE_PATH} answered ${status}. A skipped spec would hide that.`,
    )
  }
  return present
}
