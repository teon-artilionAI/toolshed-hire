/**
 * The server state cache and the rules it runs under.
 *
 * One `QueryClient` is made in main.tsx and every screen reads through it.
 * The rules sit here, in one file, so a screen cannot quietly pick its own.
 *
 * THE RETRY RULE
 * ==============
 * A read is tried again only when the API was never reached. That means
 * nothing answered, or the edge in front of the API said it could not get
 * there. It is tried at most twice more, with a wait that doubles each time.
 * An answer from the API itself is never retried. A 4xx is the API saying no,
 * and asking again gets the same no. A 5xx with a problem document is a fault
 * the API already logged, and hammering it does not help.
 *
 * A write is never retried here. A POST that timed out may still have reached
 * the server, and sending it again without an idempotency key could book the
 * same tool twice.
 *
 * HOW FRESH EACH KIND OF DATA IS
 * ==============================
 * Catalogue data, meaning branches, categories and models, changes a few times
 * a week. I treat it as fresh for a minute, so moving between screens does not
 * ask for the same list again.
 *
 * Availability is the opposite. It can change while a customer is reading the
 * page, so it is stale the moment it arrives. A screen that shows a cached
 * answer always refetches it at the same time, on mount and on focus, and a
 * failed refetch is shown as a failure and not hidden behind the old answer.
 *
 * A quote runs under the same rule. A price the server worked out a while ago
 * may no longer be the price, and a customer must never read an old one as the
 * figure they will pay.
 *
 * A reservation runs under it too. A hold lapses by itself after thirty
 * minutes and the counter can move a booking on, so a status read a while ago
 * may no longer be the status.
 *
 * The customer's own profile runs under it as well. A branch can put the
 * account on hold, and a link opened in another tab can confirm the email
 * address, and the account screen must not go on saying otherwise.
 *
 * So does a customer the counter looks up, for the same reason. Another
 * counter can put the account on hold or register the person a moment ago.
 * What the counter needs to hand equipment over sits under the reservation
 * segment, because it is the reservation read another way.
 *
 * The counter's dashboard and diary run under it too. They are left open all
 * day, and a booking is collected or a hire comes back at another counter
 * while they are on the screen, so they are read again whenever the window
 * comes back into focus. So does the asset locator, because a unit can go out
 * or come back between one search and the next.
 *
 * A hire runs under it as well. A unit can come back at the counter, a late
 * fee grows by the day and the deposit is settled the moment the last unit is
 * in, so a hire read a while ago may no longer be the hire. The customer's own
 * hires sit under the account segment and are never fresh for the same reason.
 *
 * So are the damage reports of a unit. The owner can send one for repair or
 * close it from another screen, and a counter must not offer a unit as
 * waiting for the workshop once it is back on the shelf.
 */

import { QueryClient } from '@tanstack/react-query'
import { isApiError } from '../api-problem'

/** How many times a failed read is tried again before the failure is shown. */
export const MAX_QUERY_RETRIES = 2

/** The wait before the first retry. Each later wait is double the one before. */
export const RETRY_BASE_DELAY_MS = 500

/** The longest a single wait between tries may grow to. */
export const RETRY_MAX_DELAY_MS = 4000

/** How long catalogue data counts as fresh. */
export const CATALOGUE_FRESH_MS = 60_000

/** Availability is never fresh. Every use of a cached answer refetches it. */
export const AVAILABILITY_FRESH_MS = 0

/** The first segment of every catalogue query key. */
export const CATALOGUE_KEY = 'catalogue'

/** The first segment of every availability query key. */
export const AVAILABILITY_KEY = 'availability'

/** The first segment of every quote query key. */
export const QUOTE_KEY = 'quote'

/** The first segment of every reservation query key. */
export const RESERVATIONS_KEY = 'reservations'

/** The first segment of every query key about the signed in person's own account. */
export const ACCOUNT_KEY = 'account'

/** The first segment of every query key about customers the counter looks up. */
export const CUSTOMERS_KEY = 'customers'

/** The first segment of every query key about the counter's day, which is the
 *  dashboard and the diary. */
export const COUNTER_KEY = 'counter'

/** The first segment of every query key about where units are. */
export const ASSETS_KEY = 'assets'

/** The first segment of every query key about the hires the counter reads. */
export const RENTALS_KEY = 'rentals'

/** The first segment of every query key about damage reports. */
export const DAMAGE_KEY = 'damage'

/** What never fresh means to the cache. The answer is stale when it arrives,
 *  and it is asked for again whenever a screen mounts, the window regains
 *  focus or the network comes back. Availability, quotes, reservations, the
 *  customer's own profile and hires, the customers the counter looks up, the
 *  counter's day, the locator, the hires and the damage reports all run on it. */
const NEVER_FRESH = {
  staleTime: AVAILABILITY_FRESH_MS,
  refetchOnMount: 'always',
  refetchOnWindowFocus: 'always',
  refetchOnReconnect: 'always',
} as const

/**
 * Decide whether a failed read is worth another try.
 *
 * @param failureCount How many tries have already been made again. Zero on the
 *   first failure.
 * @param error What the read threw.
 * @returns True only for a transport or gateway failure with tries left.
 */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_QUERY_RETRIES) return false
  return isApiError(error) && error.isBackendUnreachable
}

/**
 * How long to wait before the next try.
 *
 * @param failureCount Zero before the first retry, one before the second.
 * @returns The wait in milliseconds, doubling each time up to the ceiling.
 */
export function retryDelay(failureCount: number): number {
  return Math.min(RETRY_BASE_DELAY_MS * 2 ** failureCount, RETRY_MAX_DELAY_MS)
}

/** Build the cache with the rules above. Tests make their own from this too,
 *  so a test runs under the same rules the application does. */
export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      // `always` means a request is attempted even when the browser thinks it
      // is offline. The default would park the query with nothing to show. This
      // way it fails as a transport failure and the screen says so.
      queries: { retry: shouldRetry, retryDelay, networkMode: 'always' },
      mutations: { retry: false, networkMode: 'always' },
    },
  })
  client.setQueryDefaults([CATALOGUE_KEY], { staleTime: CATALOGUE_FRESH_MS })
  client.setQueryDefaults([AVAILABILITY_KEY], NEVER_FRESH)
  client.setQueryDefaults([QUOTE_KEY], NEVER_FRESH)
  client.setQueryDefaults([RESERVATIONS_KEY], NEVER_FRESH)
  client.setQueryDefaults([ACCOUNT_KEY], NEVER_FRESH)
  client.setQueryDefaults([CUSTOMERS_KEY], NEVER_FRESH)
  client.setQueryDefaults([COUNTER_KEY], NEVER_FRESH)
  client.setQueryDefaults([ASSETS_KEY], NEVER_FRESH)
  client.setQueryDefaults([RENTALS_KEY], NEVER_FRESH)
  client.setQueryDefaults([DAMAGE_KEY], NEVER_FRESH)
  return client
}
