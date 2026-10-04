/**
 * Whether the real backend has the admin catalogue routes.
 *
 * The admin catalogue spec signs the owner in, changes a late fee and puts it
 * back, and adds a model of its own to publish and hide. A backend can have
 * every earlier route without these, so the spec asks about the categories
 * and the models by name, after the session routes in backend.ts. The writes
 * were built with them. When one is not there the spec skips itself and the
 * run still passes.
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

/** The two lists. A route that is there refuses a request with no token
 *  before it looks. */
const ADMIN_CATALOGUE_PROBE_PATHS: readonly string[] = ['/api/admin/categories', '/api/admin/models']

/** The reason shown beside a skipped admin catalogue spec in the report. */
export const ADMIN_CATALOGUE_ROUTES_NEEDED =
  `This needs the admin catalogue routes on the real backend, and one of ${ADMIN_CATALOGUE_PROBE_PATHS.join(' and ')} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that can list, add and ' +
  'change categories and models and publish or hide a model.'

/**
 * Ask whether the backend has the admin catalogue routes.
 *
 * @returns True only when the session routes are there and both lists
 *   answered for themselves. An absent backend is a false and not a throw.
 */
export async function adminCatalogueRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  for (const path of ADMIN_CATALOGUE_PROBE_PATHS) {
    const status = (await request.get(path, { timeout: HEALTH_TIMEOUT_MS })).status()
    if (!ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM) continue
    if (BACKEND_IS_REQUIRED) {
      throw new Error(
        `${REQUIRE_BACKEND_VARIABLE} is set, so the admin catalogue routes have to be there, and ` +
          `GET ${path} answered ${status}. A skipped spec would hide that.`,
      )
    }
    return false
  }
  return true
}
