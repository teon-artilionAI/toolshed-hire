/**
 * Where the HTTP client and the session meet.
 *
 * The client must send the bearer token and must be able to ask for a new one,
 * and it must not know how a session is kept. The session must hand over a
 * token and renew it, and it must not know how a request is made. This file is
 * the one thing both sides import, so neither imports the other.
 *
 * The session registers two functions here when its module loads. One supplies
 * the token for a request. The other renews the session and says whether that
 * worked. Until they are registered, the client sends no token and never asks
 * for a renewal, which is also how a test of the client alone runs.
 */

import { isApiError } from '../api-problem'
import { logEvent } from './log'

/** Supplies the bearer token for a request, or null when nobody is signed in. */
export type AccessTokenProvider = () => string | null

/** Renews the session. Resolves true when there is a new token to use, and
 *  false when the session is over. It never rejects. */
export type SessionRefresher = () => Promise<boolean>

const HTTP_UNAUTHORIZED = 401

/**
 * How the `type` of a 401 problem ends when a new token would cure it.
 *
 * `session-expired` is what the session routes send. `authentication-failure`
 * is what a protected route sends for a token that is absent, expired or
 * forged. A 401 of any other type, such as a wrong password, is never retried.
 */
export const RENEWABLE_PROBLEM_TYPES: readonly string[] = [
  'session-expired',
  'authentication-failure',
]

let accessTokenProvider: AccessTokenProvider | null = null
let sessionRefresher: SessionRefresher | null = null

/**
 * Tell the client where to get the bearer token from.
 *
 * @param provider Called once per request. Pass null to go back to sending no
 *   token.
 */
export function registerAccessTokenProvider(provider: AccessTokenProvider | null): void {
  accessTokenProvider = provider
}

/**
 * Tell the client how to renew the session after a 401.
 *
 * @param refresher Called when a request was refused for want of a good token.
 *   Pass null to switch renewal off.
 */
export function registerSessionRefresher(refresher: SessionRefresher | null): void {
  sessionRefresher = refresher
}

/** The token a request should carry right now, or null. */
export function currentAccessToken(): string | null {
  return accessTokenProvider?.() ?? null
}

/** Whether the `type` of a problem ends with the given slug. */
export function problemTypeEndsWith(error: unknown, slug: string): boolean {
  return isApiError(error) && (error.problem?.type.endsWith(slug) ?? false)
}

/**
 * Whether a failure is one a new token would cure.
 *
 * @returns True only for a 401 whose problem type is one of
 *   `RENEWABLE_PROBLEM_TYPES`, and only while a refresher is registered.
 */
function isCuredByRenewal(error: unknown): boolean {
  if (sessionRefresher === null) return false
  if (!isApiError(error) || error.status !== HTTP_UNAUTHORIZED) return false
  return RENEWABLE_PROBLEM_TYPES.some((slug) => problemTypeEndsWith(error, slug))
}

/**
 * Make sure there is a token newer than the one a refused request carried.
 *
 * Several requests can be refused at once. The first one renews the session.
 * A later one may arrive here after that renewal has finished, and it must not
 * start a second one. So I compare the token the request was sent with against
 * the token held now. If they differ, the session was renewed in the meantime
 * and the request only has to be repeated.
 *
 * @param tokenSent The token the refused request carried, or null.
 * @returns True when the request is worth repeating once.
 */
async function renewAfterRefusal(tokenSent: string | null): Promise<boolean> {
  const tokenNow = currentAccessToken()
  if (tokenNow !== null && tokenNow !== tokenSent) return true
  if (sessionRefresher === null) return false
  return sessionRefresher()
}

/**
 * Run a request with the session's token, and repeat it once if a renewed
 * session would cure the refusal.
 *
 * The request is repeated once and never twice. If the repeat is refused as
 * well, that refusal is what the caller gets.
 *
 * @param attempt Makes the request with the token it is given.
 * @param call Whether renewal applies to this call, and what to name it in the
 *   log line that records the repeat.
 * @throws Whatever `attempt` throws, the first time when the refusal is not
 *   curable or the renewal failed, and the second time otherwise.
 */
export async function withSessionRenewal<Result>(
  attempt: (token: string | null) => Promise<Result>,
  call: { renew: boolean; method: string; path: string },
): Promise<Result> {
  const tokenSent = currentAccessToken()
  try {
    return await attempt(tokenSent)
  } catch (cause) {
    if (!call.renew || !isCuredByRenewal(cause)) throw cause
    if (!(await renewAfterRefusal(tokenSent))) throw cause
    logEvent('info', 'api.request_repeated', { method: call.method, path: call.path })
    return attempt(currentAccessToken())
  }
}
