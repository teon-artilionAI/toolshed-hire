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
 *
 * A healthy backend is not enough for the session spec. It needs the session
 * routes, and a backend can be up and answering without having them. So that
 * spec asks a second question, about one of those routes by name.
 *
 * The booking spec needs the reservation routes on top of the session ones,
 * and asks a third question about those.
 *
 * The account spec needs the registration and account routes, and asks a
 * fourth question about those.
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

/** One of the session routes. If it is there, the others were built with it. */
const SESSION_PROBE_PATH = '/api/auth/refresh'

/** What a backend answers for a route it does not have. 404 when nothing is
 *  mounted on the path, and 405 when the path exists for another method. */
const ROUTE_ABSENT_STATUSES: readonly number[] = [404, 405]

/** The lowest status that means the API itself did not answer properly. */
const SERVER_FAILURE_FROM = 500

/** The reason shown beside a skipped session spec in the report. */
export const SESSION_ROUTES_NEEDED =
  `This needs the session routes on the real backend, and POST ${SESSION_PROBE_PATH} answered ` +
  'as a route that is not there. Run the browser tests again against a backend that has ' +
  'login, refresh and logout.'

/**
 * Ask whether the backend has the session routes.
 *
 * I post to refresh with no cookie. A backend that has the route refuses that
 * with a 401, which is an answer from the route and so proves it exists. A
 * backend that does not have it answers 404 or 405.
 *
 * @returns True only when the backend is healthy and the route answered for
 *   itself. An absent backend is a false and not a throw.
 */
export async function sessionRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await backendIsReachable(request))) return false
  const response = await request.post(SESSION_PROBE_PATH, { timeout: HEALTH_TIMEOUT_MS })
  const status = response.status()
  const present = !ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM
  if (!present && BACKEND_IS_REQUIRED) {
    throw new Error(
      `${REQUIRE_BACKEND_VARIABLE} is set, so the session routes have to be there, and ` +
        `POST ${SESSION_PROBE_PATH} answered ${status}. A skipped spec would hide that.`,
    )
  }
  return present
}

/** One of the reservation routes. If it is there, the others were built with it. */
const RESERVATION_PROBE_PATH = '/api/reservations'

/** The reason shown beside a skipped booking spec in the report. */
export const RESERVATION_ROUTES_NEEDED =
  `This needs the reservation routes on the real backend, and GET ${RESERVATION_PROBE_PATH} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that ' +
  'can create, hold, confirm, cancel, list and read a reservation.'

/**
 * Ask whether the backend has the reservation routes.
 *
 * I ask for the list with no token. A backend that has the route refuses that
 * with a 401, which is an answer from the route and so proves it exists. A
 * backend that does not have it answers 404 or 405. The booking spec signs a
 * customer in, so the session routes have to be there as well.
 *
 * @returns True only when the backend is healthy, has the session routes, and
 *   the reservation route answered for itself. An absent backend is a false
 *   and not a throw.
 */
export async function reservationRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  const response = await request.get(RESERVATION_PROBE_PATH, { timeout: HEALTH_TIMEOUT_MS })
  const status = response.status()
  const present = !ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM
  if (!present && BACKEND_IS_REQUIRED) {
    throw new Error(
      `${REQUIRE_BACKEND_VARIABLE} is set, so the reservation routes have to be there, and ` +
        `GET ${RESERVATION_PROBE_PATH} answered ${status}. A skipped spec would hide that.`,
    )
  }
  return present
}

/** One of the registration and account routes. If it is there, the others
 *  were built with it. */
const ACCOUNT_PROBE_PATH = '/api/me/profile'

/** The reason shown beside a skipped account spec in the report. */
export const ACCOUNT_ROUTES_NEEDED =
  `This needs the registration and account routes on the real backend, and GET ${ACCOUNT_PROBE_PATH} ` +
  'answered as a route that is not there. Run the browser tests again against a backend that ' +
  'can register a customer, reset a password and read and change a profile.'

/**
 * Ask whether the backend has the registration and account routes.
 *
 * I ask for the profile with no token. A backend that has the route refuses
 * that with a 401, which is an answer from the route and so proves it exists.
 * A backend that does not have it answers 404 or 405. The account spec signs a
 * new customer in, so the session routes have to be there as well.
 *
 * @returns True only when the backend is healthy, has the session routes, and
 *   the profile route answered for itself. An absent backend is a false and
 *   not a throw.
 */
export async function accountRoutesArePresent(request: APIRequestContext): Promise<boolean> {
  if (!(await sessionRoutesArePresent(request))) return false
  const response = await request.get(ACCOUNT_PROBE_PATH, { timeout: HEALTH_TIMEOUT_MS })
  const status = response.status()
  const present = !ROUTE_ABSENT_STATUSES.includes(status) && status < SERVER_FAILURE_FROM
  if (!present && BACKEND_IS_REQUIRED) {
    throw new Error(
      `${REQUIRE_BACKEND_VARIABLE} is set, so the registration and account routes have to be ` +
        `there, and GET ${ACCOUNT_PROBE_PATH} answered ${status}. A skipped spec would hide that.`,
    )
  }
  return present
}
