/**
 * The two markers the session keeps in web storage.
 *
 * This is the only file that touches web storage for the session, and the
 * only one that touches `localStorage` at all. Each marker is a fixed word
 * under a fixed key there. Neither names an account and neither holds a token.
 * The access token is never written to web storage, and the refresh token is
 * in a cookie this code cannot read.
 *
 * The hire basket is the one other thing kept in web storage. It has a file of
 * its own, basket-storage.ts, and a key of its own in `sessionStorage`.
 *
 * THE SESSION HINT
 * ================
 * Whether there is a session is known only to the server, through the refresh
 * cookie. Asking on every page load means a visitor who never signed in costs
 * a request, and the 401 that answers it shows as an error in the console. So
 * a sign in or a renewal that works leaves this hint, and start-up only asks
 * the server while it is there. With no hint the person is simply signed out.
 * The hint goes when the person signs out and when the server says the session
 * is over.
 *
 * A SIGN OUT THE SERVER NEVER HEARD
 * =================================
 * Signing out drops the access token whatever the server says. When the call
 * fails, the refresh cookie is still in the browser, and only the server can
 * end it. This marker records that. While it is there, start-up sends the sign
 * out again and does not carry the session on. It goes once the server
 * confirms a sign out, and at a new sign in, because the server then replaces
 * the cookie it was about.
 *
 * A browser can refuse web storage altogether. That is logged and never
 * thrown, because signing in and out of the page still works without it.
 */

import { logEvent } from './api/log'

/** Present while this browser may hold a session worth asking about. */
export const SESSION_HINT_KEY = 'toolshed.session-hint'

/** Present while the server still has to be told about a sign out. */
export const SIGN_OUT_OWED_KEY = 'toolshed.sign-out-owed'

/** What every marker holds. Only its presence is ever read. */
export const MARKER_VALUE = 'yes'

/** Every key the session may leave in web storage. */
export const SESSION_MARKER_KEYS: readonly string[] = [SESSION_HINT_KEY, SIGN_OUT_OWED_KEY]

/** What went wrong with web storage, in words fit for a log line. */
function context(operation: string, key: string, cause: unknown): Record<string, unknown> {
  return {
    operation,
    key,
    reason: cause instanceof Error ? `${cause.name} ${cause.message}` : String(cause),
  }
}

/**
 * @param whenUnreadable What to answer when web storage cannot be read at all.
 */
function isSet(key: string, whenUnreadable: boolean): boolean {
  try {
    return window.localStorage.getItem(key) !== null
  } catch (cause) {
    logEvent('warn', 'session.marker_unreadable', context('read', key, cause))
    return whenUnreadable
  }
}

function set(key: string): void {
  try {
    window.localStorage.setItem(key, MARKER_VALUE)
  } catch (cause) {
    logEvent('warn', 'session.marker_not_kept', context('write', key, cause))
  }
}

function clear(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch (cause) {
    logEvent('warn', 'session.marker_not_cleared', context('remove', key, cause))
  }
}

/**
 * Whether it is worth asking the server for a session at start-up.
 *
 * @returns True while the hint is there. Also true when web storage cannot be
 *   read, because then no hint could ever be kept, and never asking would sign
 *   the person out on every reload.
 */
export function sessionMayExist(): boolean {
  return isSet(SESSION_HINT_KEY, true)
}

/** Leave the hint, after a sign in or a renewal the server accepted. */
export function noteSessionMayExist(): void {
  set(SESSION_HINT_KEY)
}

/** Remove the hint, at a sign out or once the server says the session is over. */
export function noteNoSession(): void {
  clear(SESSION_HINT_KEY)
}

/**
 * Whether an earlier sign out never reached the server.
 *
 * @returns False when the marker is absent, and also when web storage cannot
 *   be read, in which case none could have been written either.
 */
export function isSignOutOwed(): boolean {
  return isSet(SIGN_OUT_OWED_KEY, false)
}

/** Leave the marker, after a sign out the server did not confirm. */
export function noteSignOutOwed(): void {
  set(SIGN_OUT_OWED_KEY)
}

/** Remove the marker, once the server has confirmed a sign out or a sign in. */
export function clearSignOutOwed(): void {
  clear(SIGN_OUT_OWED_KEY)
}
