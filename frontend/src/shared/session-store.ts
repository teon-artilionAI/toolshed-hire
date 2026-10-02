/**
 * The session, held outside React.
 *
 * WHERE THE ACCESS TOKEN LIVES
 * ============================
 * In `accessToken` below, a variable closed over by this module, and nowhere
 * else. It is never written to `localStorage`, `sessionStorage`, a cookie or a
 * log, and it is not part of the snapshot the screens read. A script injected
 * into the page can read web storage, and it cannot read a variable no module
 * exports. The token is short lived, and a reload simply asks for a new one.
 *
 * WHAT SURVIVES A RELOAD
 * ======================
 * The refresh cookie does. The server sets it HttpOnly, so this code cannot
 * read it and does not try. On start-up I call refresh once, and only when
 * this browser has held a session before. If the cookie is good the server
 * answers with a new access token and the account, and the person is still
 * signed in. If it is not, they are signed out. Until that answer arrives the
 * status is `checking`, and the application shows a neutral loading state and
 * no screen.
 *
 * ONE RENEWAL AT A TIME
 * =====================
 * `renewSession` shares one request among everybody who asks while it is in
 * flight. The server replaces the refresh cookie each time it is used, so two
 * refreshes racing each other would leave one of them holding a cookie that
 * has already been spent. It runs at start-up, and again when a request made
 * by a signed in person is refused for want of a good token.
 *
 * WHAT IS KEPT IN WEB STORAGE
 * ===========================
 * Two markers, both in session-markers.ts, and no token. One says this browser
 * may hold a session, so a visitor who never signed in costs no request at
 * start-up. The other says a sign out never reached the server, so start-up
 * sends it again and does not carry the session on.
 *
 * This module registers itself with the HTTP client when it loads, through
 * api/session-seam.ts. That is the only wiring there is.
 */

import { isApiError } from './api-problem'
import { SESSION_EXPIRED, login, logout, refreshSession } from './api/auth'
import type { SessionGrant, SessionUser } from './api/contract'
import { logEvent } from './api/log'
import {
  problemTypeEndsWith,
  registerAccessTokenProvider,
  registerSessionRefresher,
} from './api/session-seam'
import * as markers from './session-markers'

/**
 * - `checking`: start-up has not found out yet whether there is a session.
 * - `signedIn`: there is an access token and an account.
 * - `signedOut`: there is neither.
 */
export type SessionStatus = 'checking' | 'signedIn' | 'signedOut'

/** What the screens may know about the session. The token is not in it. */
export interface SessionSnapshot {
  status: SessionStatus
  user: SessionUser | null
  /**
   * `expired` when the session ended underneath a person who was signed in,
   * so the sign in screen can say so. Null when they signed out themselves,
   * when there was no session to begin with, and while one is running.
   */
  endedBecause: 'expired' | null
}

type Listener = () => void

const CHECKING: SessionSnapshot = { status: 'checking', user: null, endedBecause: null }

let accessToken: string | null = null
let snapshot: SessionSnapshot = CHECKING
const listeners = new Set<Listener>()

/** The renewal in flight, shared by everybody who asks while it runs. */
let renewal: Promise<boolean> | null = null
/** The start-up check. Made once, however often the application asks. */
let startUp: Promise<void> | null = null
/** The sign out in flight, so pressing the button twice makes one call. */
let leaving: Promise<void> | null = null
/**
 * Counts every time the person signs in or out. A renewal that was already in
 * flight compares the count before and after, and leaves the session alone if
 * the person has acted in the meantime.
 */
let personActed = 0

function publish(next: SessionSnapshot): void {
  snapshot = next
  listeners.forEach((listener) => listener())
}

function hold(grant: SessionGrant): void {
  accessToken = grant.accessToken
  markers.noteSessionMayExist()
  publish({ status: 'signedIn', user: grant.user, endedBecause: null })
}

function drop(endedBecause: SessionSnapshot['endedBecause']): void {
  accessToken = null
  publish({ status: 'signedOut', user: null, endedBecause })
}

/** Why a call failed, in words fit for a log line. Never the token. */
function reasonOf(cause: unknown): Record<string, unknown> {
  if (isApiError(cause)) {
    return {
      kind: cause.kind,
      status: cause.status,
      problem_type: cause.problem?.type ?? null,
      request_id: cause.requestId,
    }
  }
  return { reason: cause instanceof Error ? cause.message : String(cause) }
}

function renewalSucceeded(grant: SessionGrant, startedAt: number): boolean {
  if (personActed !== startedAt) return snapshot.status === 'signedIn'
  hold(grant)
  logEvent('info', 'session.renewed', { role: grant.user.role, expires_in: grant.expiresIn })
  return true
}

function renewalFailed(cause: unknown, startedAt: number): boolean {
  if (personActed !== startedAt) return snapshot.status === 'signedIn'
  const wasSignedIn = snapshot.status === 'signedIn'
  const noSession = problemTypeEndsWith(cause, SESSION_EXPIRED)
  // The hint goes only when the server says the session is over. When the
  // server could not be asked, the cookie may still be good at the next load.
  if (noSession) markers.noteNoSession()
  if (wasSignedIn) {
    logEvent('warn', 'session.ended', { operation: 'refresh', ...reasonOf(cause) })
  } else if (noSession) {
    logEvent('info', 'session.none_found', { operation: 'refresh' })
  } else {
    // The API did not say there was no session. It could not be asked, or it
    // answered with something else. I cannot hold a session I cannot confirm.
    logEvent('warn', 'session.check_failed', { operation: 'refresh', ...reasonOf(cause) })
  }
  drop(wasSignedIn ? 'expired' : null)
  return false
}

/**
 * Renew the session through the refresh cookie.
 *
 * Callers that arrive while a renewal is in flight share it. A failure signs
 * the person out. It is reported as `expired` only when they were signed in.
 *
 * @returns True when there is a good access token afterwards. Never rejects.
 */
export function renewSession(): Promise<boolean> {
  if (renewal === null) {
    const startedAt = personActed
    renewal = refreshSession()
      .then(
        (grant) => renewalSucceeded(grant, startedAt),
        (cause: unknown) => renewalFailed(cause, startedAt),
      )
      .finally(() => {
        renewal = null
      })
  }
  return renewal
}

/**
 * Tell the server the session is over, and leave a note when it cannot be told.
 *
 * @returns True when the server confirmed it. Never rejects.
 */
function tellServerOfSignOut(): Promise<boolean> {
  return logout().then(
    () => {
      markers.clearSignOutOwed()
      logEvent('info', 'session.signed_out', { confirmed_by_server: true })
      return true
    },
    (cause: unknown) => {
      markers.noteSignOutOwed()
      logEvent('warn', 'session.signed_out', { confirmed_by_server: false, ...reasonOf(cause) })
      return false
    },
  )
}

/** The start-up check itself. `startSession` makes sure it runs once. */
async function findSession(): Promise<void> {
  if (markers.isSignOutOwed()) {
    // The person signed out and the server never heard. The refresh cookie may
    // still be good, and using it would sign them back in. I send the sign out
    // again and stay signed out, whether or not it gets through this time.
    const startedAt = personActed
    logEvent('info', 'session.sign_out_owed', { operation: 'logout' })
    await tellServerOfSignOut()
    if (personActed === startedAt) drop(null)
  } else if (markers.sessionMayExist()) {
    await renewSession()
  } else {
    // Nobody has signed in from this browser, so there is nothing to ask for.
    logEvent('info', 'session.none_expected', { operation: 'start-up', asked_server: false })
    drop(null)
  }
}

/**
 * Find out, once, whether there is a session to carry on with.
 *
 * Safe to call any number of times. Only the first call asks the server.
 */
export function startSession(): Promise<void> {
  startUp ??= findSession()
  return startUp
}

/**
 * Sign in with an email address and a password.
 *
 * @returns The account that is now signed in.
 * @throws ApiError as `login` in api/auth.ts describes. The session is left
 *   as it was when the sign in is refused.
 */
export async function signIn(email: string, password: string): Promise<SessionUser> {
  const grant = await login({ email, password })
  personActed += 1
  // The server has just replaced the refresh cookie, so an older sign out it
  // never heard about no longer has a cookie to end.
  markers.clearSignOutOwed()
  hold(grant)
  logEvent('info', 'session.signed_in', { role: grant.user.role, expires_in: grant.expiresIn })
  return grant.user
}

/**
 * Sign out. Tells the server, then drops the token whatever the server said.
 *
 * The token goes even when the call fails, because the person asked to be
 * signed out of this page and must not be left looking at a signed in one.
 * The failure is logged, and a note is left so the next page load sends the
 * sign out again before it does anything with the refresh cookie.
 */
export function signOut(): Promise<void> {
  leaving ??= tellServerOfSignOut()
    .then(() => {
      personActed += 1
      markers.noteNoSession()
      drop(null)
    })
    .finally(() => {
      leaving = null
    })
  return leaving
}

/** Call `listener` whenever the snapshot changes. Returns the way to stop. */
export function subscribeToSession(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The session as it stands. The same object until something changes. */
export function sessionSnapshot(): SessionSnapshot {
  return snapshot
}

/**
 * Put the module back to how it was when it loaded.
 *
 * Only the test setup calls this, so one test cannot leave a signed in
 * session behind for the next. For the application a page load does it.
 */
export function resetSessionForTests(): void {
  accessToken = null
  snapshot = CHECKING
  renewal = null
  startUp = null
  leaving = null
  personActed += 1
  listeners.clear()
}

/**
 * What the client asks for after a request was refused with a 401.
 *
 * Only a person who is signed in has a session to renew. For anybody else a
 * 401 means what it says. In particular a person who has signed out stays
 * signed out, and no request made afterwards can quietly sign them in again.
 */
function renewForRefusedRequest(): Promise<boolean> {
  return snapshot.status === 'signedIn' ? renewSession() : Promise.resolve(false)
}

registerAccessTokenProvider(() => accessToken)
registerSessionRefresher(renewForRefusedRequest)
