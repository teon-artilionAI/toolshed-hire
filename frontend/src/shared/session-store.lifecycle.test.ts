/**
 * Tests for what happens to a session after it has begun.
 *
 * Its token stops working and is renewed, or cannot be. The person signs out,
 * and stays signed out even when the server never heard. Where the token is
 * kept through all of it is in web-storage.test.ts.
 *
 * As in session-store.test.ts, only `fetch` is replaced.
 */

import { describe, expect, it, vi } from 'vitest'
import { getCurrentUser } from './api/auth'
import { jsonResponse, mockApi, noContentResponse, problemResponse } from '../test/api-mock'
import {
  ACCESS_TOKEN,
  CUSTOMER,
  LOGIN_ROUTE,
  LOGOUT_ROUTE,
  ME_ROUTE,
  REFRESH_ROUTE,
  bearerOf,
  failureOf,
  grantFor,
  meAccepting,
  sessionExpired,
  tokenRefused,
} from '../test/session-samples'
import { renewSession, sessionSnapshot, signIn, signOut, startSession } from './session-store'
import { MARKER_VALUE, SIGN_OUT_OWED_KEY } from './session-markers'

const RENEWED_TOKEN = 'renewed-access-token-2c8e4d6f'
const PASSWORD = 'a-password-typed-by-a-person'

function unreachable(): never {
  throw new TypeError('Failed to fetch')
}

function signOutIsOwed(): boolean {
  return window.localStorage.getItem(SIGN_OUT_OWED_KEY) !== null
}

/** Everything in `localStorage`, as plain keys and values. */
function stored(): Record<string, string> {
  return { ...window.localStorage }
}

describe('a session whose token has stopped working', () => {
  it('shares one refresh among requests refused together, and repeats each once', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER, RENEWED_TOKEN)),
      [ME_ROUTE]: meAccepting(RENEWED_TOKEN),
    })
    await signIn(CUSTOMER.email, PASSWORD)

    const answers = await Promise.all([getCurrentUser(), getCurrentUser(), getCurrentUser()])

    expect(answers).toEqual([CUSTOMER, CUSTOMER, CUSTOMER])
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(ME_ROUTE).map(bearerOf)).toEqual([
      ACCESS_TOKEN,
      ACCESS_TOKEN,
      ACCESS_TOKEN,
      RENEWED_TOKEN,
      RENEWED_TOKEN,
      RENEWED_TOKEN,
    ])
    expect(sessionSnapshot().status).toBe('signedIn')
  })

  it('repeats a request once, and gives up when the repeat is refused too', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER, RENEWED_TOKEN)),
      [ME_ROUTE]: () => tokenRefused(),
    })
    await signIn(CUSTOMER.email, PASSWORD)

    const error = await failureOf(getCurrentUser())

    expect(error.status).toBe(401)
    expect(network.requestsTo(ME_ROUTE)).toHaveLength(2)
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
  })

  it('signs the person out as expired when the refresh fails', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [REFRESH_ROUTE]: () => sessionExpired(),
      [ME_ROUTE]: () => tokenRefused(),
    })
    await signIn(CUSTOMER.email, PASSWORD)

    const error = await failureOf(getCurrentUser())

    expect(error.status).toBe(401)
    expect(sessionSnapshot()).toEqual({ status: 'signedOut', user: null, endedBecause: 'expired' })
    // The request was not repeated, and no later request carries the old token.
    expect(network.requestsTo(ME_ROUTE)).toHaveLength(1)
    await failureOf(getCurrentUser())
    expect(bearerOf(network.requestsTo(ME_ROUTE)[1])).toBeNull()
  })

  it('does not try to renew anything for a person who is signed out', async () => {
    const network = mockApi({
      [REFRESH_ROUTE]: () => sessionExpired(),
      [ME_ROUTE]: () => tokenRefused(),
    })
    await startSession()

    const error = await failureOf(getCurrentUser())

    expect(error.status).toBe(401)
    // Only the start-up check asked. The refused request did not.
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(ME_ROUTE)).toHaveLength(1)
  })

  it('never rejects from a renewal, and says whether it worked', async () => {
    mockApi({ [REFRESH_ROUTE]: () => problemResponse(500) })

    await expect(renewSession()).resolves.toBe(false)
  })
})

describe('signing out', () => {
  it('tells the server and drops the token', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: () => noContentResponse(),
      [REFRESH_ROUTE]: () => sessionExpired(),
      [ME_ROUTE]: meAccepting(ACCESS_TOKEN),
    })
    await signIn(CUSTOMER.email, PASSWORD)

    await signOut()

    expect(sessionSnapshot()).toEqual({ status: 'signedOut', user: null, endedBecause: null })
    // Nothing is left behind, so the next load asks the server nothing.
    expect(stored()).toEqual({})
    const [request] = network.requestsTo(LOGOUT_ROUTE)
    expect(request.body).toBeUndefined()
    expect(request.credentials).toBe('include')
    await failureOf(getCurrentUser())
    expect(bearerOf(network.requestsTo(ME_ROUTE)[0])).toBeNull()
  })

  it('is not undone by a later request, even while the refresh cookie still works', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: () => noContentResponse(),
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER, RENEWED_TOKEN)),
      [ME_ROUTE]: () => tokenRefused(),
    })
    await signIn(CUSTOMER.email, PASSWORD)
    await signOut()

    await failureOf(getCurrentUser())

    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(0)
    expect(sessionSnapshot().status).toBe('signedOut')
  })

  it('drops the token even when the server cannot be told, and notes that it is owed', async () => {
    mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: unreachable,
    })
    await signIn(CUSTOMER.email, PASSWORD)

    await signOut()

    expect(sessionSnapshot().status).toBe('signedOut')
    // The marker says a sign out is owed and nothing about whose it was.
    expect(stored()).toEqual({ [SIGN_OUT_OWED_KEY]: MARKER_VALUE })
  })

  it('makes one call when it is asked for twice at once', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: () => noContentResponse(),
    })
    await signIn(CUSTOMER.email, PASSWORD)

    await Promise.all([signOut(), signOut()])

    expect(network.requestsTo(LOGOUT_ROUTE)).toHaveLength(1)
  })
})

describe('a sign out the server never heard', () => {
  it('is sent again at start-up, and the cookie is not used to carry the session on', async () => {
    window.localStorage.setItem(SIGN_OUT_OWED_KEY, MARKER_VALUE)
    const network = mockApi({
      [LOGOUT_ROUTE]: () => noContentResponse(),
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
    })

    await startSession()

    expect(sessionSnapshot()).toEqual({ status: 'signedOut', user: null, endedBecause: null })
    expect(network.requestsTo(LOGOUT_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(0)
    expect(signOutIsOwed()).toBe(false)
  })

  it('stays owed, and the person stays signed out, while the server still cannot be told', async () => {
    window.localStorage.setItem(SIGN_OUT_OWED_KEY, MARKER_VALUE)
    const network = mockApi({
      [LOGOUT_ROUTE]: unreachable,
      [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
    })

    await startSession()

    expect(sessionSnapshot().status).toBe('signedOut')
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(0)
    expect(signOutIsOwed()).toBe(true)
  })

  it('is no longer owed once the person signs in again', async () => {
    window.localStorage.setItem(SIGN_OUT_OWED_KEY, MARKER_VALUE)
    mockApi({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) })

    await signIn(CUSTOMER.email, PASSWORD)

    expect(signOutIsOwed()).toBe(false)
  })

  it('still signs the person out of the page when the browser refuses web storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
    mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [LOGOUT_ROUTE]: unreachable,
    })
    await signIn(CUSTOMER.email, PASSWORD)

    await signOut()

    expect(sessionSnapshot().status).toBe('signedOut')
    setItem.mockRestore()
  })
})
