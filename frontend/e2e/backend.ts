/**
 * Whether the real backend is there to test against.
 *
 * The catalogue specs need the API and a seeded database behind it. The
 * preview server proxies `/api` to the local backend, so I ask the health
 * endpoint through the same address the page uses. When nothing healthy
 * answers, those specs skip themselves and say why, and the run still passes.
 *
 * A degraded backend counts as absent. The health endpoint answers 503 when
 * the database is down, and the catalogue cannot load from that either.
 */

import type { APIRequestContext } from '@playwright/test'

/** The health endpoint, through the preview server's proxy. */
const HEALTH_PATH = '/api/health'

/** How long the health check may take. A backend that is there answers at once. */
const HEALTH_TIMEOUT_MS = 5000

/** Set in the pipeline, where the API is started for the browser tests. There a
 *  missing backend is a failure. On my machine it is a reason to skip. */
const REQUIRE_BACKEND_VARIABLE = 'E2E_REQUIRE_BACKEND'
const BACKEND_IS_REQUIRED = Boolean(process.env[REQUIRE_BACKEND_VARIABLE])

/** The reason shown beside a skipped spec in the report. */
export const BACKEND_NEEDED =
  'This needs the real backend with seeded data, and /api/health did not answer OK. ' +
  'Start the backend on port 8000 and run the browser tests again.'

/**
 * Ask the health endpoint whether the backend is up.
 *
 * @returns True only for a 2xx answer. The proxy answers with a 5xx of its own
 *   when nothing is listening, so an absent backend is a false and not a throw.
 */
export async function backendIsReachable(request: APIRequestContext): Promise<boolean> {
  const response = await request.get(HEALTH_PATH, { timeout: HEALTH_TIMEOUT_MS })
  if (!response.ok() && BACKEND_IS_REQUIRED) {
    throw new Error(
      `${REQUIRE_BACKEND_VARIABLE} is set, so the backend has to be there, and ` +
        `${HEALTH_PATH} answered ${response.status()}. A skipped spec would hide that.`,
    )
  }
  return response.ok()
}
