/**
 * Whether the real backend has the asset register routes.
 *
 * The asset register spec signs the owner in, registers a unit of its own,
 * moves it through its lifecycle and retires it. A backend can have every
 * earlier route without these, so the spec asks about the register by name,
 * after the session routes in backend.ts. The writes were built with it. It
 * also searches the models to choose one, so it asks about the owner's models
 * too. When one is not there the spec skips itself and the run still passes.
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

/** The register and the models. A route that is there refuses a request with
 *  no token before it looks. */
const ASSET_REGISTER_PROBE_PATHS: readonly string[] = ['/api/admin/assets', '/api/admin/models']

/** The reason shown beside a skipped asset register spec in the report. */
export const ASSET_REGISTER_ROUTES_NEEDED =
  `This needs the asset register routes on the real backend, and one of ${ASSET_REGISTER_PROBE_PATHS.join(' and ')} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that can list, read, ' +
  'register, change and move the units of the fleet.'

/**
 * Ask whether the backend has the asset register routes.
 *
 * @returns True only when the session routes are there and both lists
 *   answered for themselves. An absent backend is a false and not a throw.
 */
export async function assetRegisterRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  for (const path of ASSET_REGISTER_PROBE_PATHS) {
    const status = (await request.get(path, { timeout: HEALTH_TIMEOUT_MS })).status()
    if (!ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM) continue
    if (BACKEND_IS_REQUIRED) {
      throw new Error(
        `${REQUIRE_BACKEND_VARIABLE} is set, so the asset register routes have to be there, and ` +
          `GET ${path} answered ${status}. A skipped spec would hide that.`,
      )
    }
    return false
  }
  return true
}
