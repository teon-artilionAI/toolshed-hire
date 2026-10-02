/**
 * Where the hire basket is kept between reloads.
 *
 * This is the only file that touches `sessionStorage`. The basket is one JSON
 * string under one fixed key. It lives for as long as the tab does, so a
 * reload keeps it and closing the tab ends it. It holds the dates, a branch
 * code, model slugs and quantities, and the id of a booking that is under way.
 * It holds no name, no address and no token.
 *
 * The session keeps its own two markers in `localStorage`, through
 * session-markers.ts. The two files share nothing, so neither can write under
 * the other's key.
 *
 * A browser can refuse web storage altogether. That is logged and never
 * thrown, because the basket still works in memory without it. It then lasts
 * until the next reload.
 */

import { logEvent } from './api/log'

/** The one key the basket is kept under. */
export const BASKET_STORAGE_KEY = 'toolshed.basket'

/** What went wrong with web storage, in words fit for a log line. */
function context(operation: string, cause: unknown): Record<string, unknown> {
  return {
    operation,
    key: BASKET_STORAGE_KEY,
    reason: cause instanceof Error ? `${cause.name} ${cause.message}` : String(cause),
  }
}

/** What is stored for the basket, or null when nothing is or it cannot be read. */
export function readStoredBasket(): string | null {
  try {
    return window.sessionStorage.getItem(BASKET_STORAGE_KEY)
  } catch (cause) {
    logEvent('warn', 'basket.storage_unreadable', context('read', cause))
    return null
  }
}

/** Keep the basket, already written out as JSON. */
export function writeStoredBasket(serialised: string): void {
  try {
    window.sessionStorage.setItem(BASKET_STORAGE_KEY, serialised)
  } catch (cause) {
    logEvent('warn', 'basket.storage_not_kept', context('write', cause))
  }
}

/** Remove the basket, so an empty one leaves nothing behind. */
export function clearStoredBasket(): void {
  try {
    window.sessionStorage.removeItem(BASKET_STORAGE_KEY)
  } catch (cause) {
    logEvent('warn', 'basket.storage_not_cleared', context('remove', cause))
  }
}
