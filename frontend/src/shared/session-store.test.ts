/**
 * Tests for the session itself, from start-up to a sign in.
 *
 * I replace `fetch` and nothing else, so the real client, the real renewal
 * rule and the real session run together. Each test says how the session
 * routes answer and then looks at two things. What the screens would be told,
 * and what went over the wire.
 *
 * What happens to a session afterwards is in session-store.lifecycle.test.ts.
 * The setup file puts the session back to how it starts after every test.
 */

import { describe, expect, it, vi } from 'vitest'
import { getCurrentUser } from './api/auth'
import { jsonResponse, mockApi } from '../test/api-mock'
import {
  ACCESS_TOKEN,
  COUNTER_STAFF,
  CUSTOMER,
  LOGIN_ROUTE,
  ME_ROUTE,
  REFRESH_ROUTE,
  bearerOf,
  failureOf,
  grantFor,
  invalidCredentials,
  meAccepting,
  sessionExpired,
  tooManyAttempts,
} from '../test/session-samples'
import { SESSION_HINT_KEY } from './session-markers'
import { sessionSnapshot, signIn, startSession, subscribeToSession } from './session-store'

const PASSWORD = 'a-password-typed-by-a-person'

/** Whether the browser is marked as one that may hold a session. The test
 *  setup sets the mark before every test, and a first visit removes it. */
function hasSessionHint(): boolean {
  return window.localStorage.getItem(SESSION_HINT_KEY) !== null
}

describe('start-up in a browser that has never held a session', () => {
  it('is signed out at once and asks the server nothing', async () => {
    window.localStorage.removeItem(SESSION_HINT_KEY)
    const network = mockApi({ [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) })

    const started = startSession()

    // Already settled, with no loading state to wait through.
    expect(sessionSnapshot()).toEqual({ status: 'signedOut', user: null, endedBecause: null })
    await started
    expect(network.requests).toHaveLength(0)
    expect(hasSessionHint()).toBe(false)
  })
})

describe('start-up', () => {
  it('is checking until the server has answered', () => {
    mockApi({ [REFRESH_ROUTE]: () => new Promise<Response>(() => {}) })

    void startSession()

    expect(sessionSnapshot()).toEqual({ status: 'checking', user: null, endedBecause: null })
  })

  it('carries on a session the refresh cookie still holds', async () => {
    const network = mockApi({ [REFRESH_ROUTE]: () => jsonResponse(grantFor(COUNTER_STAFF)) })

    await startSession()

    expect(sessionSnapshot()).toEqual({
      status: 'signedIn',
      user: COUNTER_STAFF,
      endedBecause: null,
    })
    const [request] = network.requestsTo(REFRESH_ROUTE)
    expect(request.body).toBeUndefined()
    expect(request.credentials).toBe('include')
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
    expect(hasSessionHint()).toBe(true)
  })

  it('is signed out, and not called expired, when there is no session', async () => {
    const network = mockApi({ [REFRESH_ROUTE]: () => sessionExpired() })

    await startSession()

    expect(sessionSnapshot()).toEqual({ status: 'signedOut', user: null, endedBecause: null })
    // The server was asked once, and its answer means the next load need not ask.
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
    expect(hasSessionHint()).toBe(false)
  })

  it('is signed out when the API cannot be reached', async () => {
    mockApi({
      [REFRESH_ROUTE]: () => {
        throw new TypeError('Failed to fetch')
      },
    })

    await startSession()

    expect(sessionSnapshot().status).toBe('signedOut')
    // Nobody said the session is over, so the next load asks again.
    expect(hasSessionHint()).toBe(true)
  })

  it('asks the server once, however often it is called', async () => {
    const network = mockApi({ [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) })

    await Promise.all([startSession(), startSession()])
    await startSession()

    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
  })

  it('tells a subscriber when the answer arrives', async () => {
    mockApi({ [REFRESH_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) })
    const listener = vi.fn()
    const stop = subscribeToSession(listener)

    await startSession()
    stop()

    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('signing in', () => {
  it('sends what was typed and holds the session that comes back', async () => {
    const network = mockApi({
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)),
      [ME_ROUTE]: meAccepting(ACCESS_TOKEN),
    })

    const user = await signIn(CUSTOMER.email, PASSWORD)

    expect(user).toEqual(CUSTOMER)
    expect(sessionSnapshot()).toEqual({ status: 'signedIn', user: CUSTOMER, endedBecause: null })
    expect(hasSessionHint()).toBe(true)
    expect(network.requestsTo(LOGIN_ROUTE)[0].body).toEqual({
      email: CUSTOMER.email,
      password: PASSWORD,
    })
    // The next request carries the token, which is the only way to see it.
    await getCurrentUser()
    expect(bearerOf(network.requestsTo(ME_ROUTE)[0])).toBe(ACCESS_TOKEN)
  })

  it('throws the refusal and stays signed out when the details are wrong', async () => {
    const network = mockApi({
      [REFRESH_ROUTE]: () => sessionExpired(),
      [LOGIN_ROUTE]: () => invalidCredentials(),
    })
    await startSession()

    const error = await failureOf(signIn(CUSTOMER.email, 'wrong'))

    expect(error.status).toBe(401)
    expect(error.problem?.type.endsWith('invalid-credentials')).toBe(true)
    expect(sessionSnapshot().status).toBe('signedOut')
    // A refused sign in is not answered with an attempt to renew anything.
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(LOGIN_ROUTE)).toHaveLength(1)
  })

  it('carries the wait the server named when there were too many attempts', async () => {
    mockApi({ [LOGIN_ROUTE]: () => tooManyAttempts(90) })

    const error = await failureOf(signIn(CUSTOMER.email, PASSWORD))

    expect(error.status).toBe(429)
    expect(error.retryAfterSeconds).toBe(90)
  })

  it('throws a transport failure when the API cannot be reached', async () => {
    mockApi({
      [LOGIN_ROUTE]: () => {
        throw new TypeError('Failed to fetch')
      },
    })

    const error = await failureOf(signIn(CUSTOMER.email, PASSWORD))

    expect(error.isBackendUnreachable).toBe(true)
  })

  it('refuses an answer that names a role the contract does not have', async () => {
    mockApi({
      [LOGIN_ROUTE]: () => jsonResponse({ ...grantFor(CUSTOMER), user: { ...CUSTOMER, role: 'owner' } }),
    })

    const error = await failureOf(signIn(CUSTOMER.email, PASSWORD))

    expect(error.kind).toBe('malformed')
    expect(sessionSnapshot().user).toBeNull()
  })

  it('reads a branch code that was left out as null', async () => {
    const { branchCode: _omitted, ...withoutBranch } = CUSTOMER
    mockApi({ [LOGIN_ROUTE]: () => jsonResponse({ ...grantFor(CUSTOMER), user: withoutBranch }) })

    const user = await signIn(CUSTOMER.email, PASSWORD)

    expect(user.branchCode).toBeNull()
  })

  it('carries whether email can reach the address of the account', async () => {
    mockApi({ [LOGIN_ROUTE]: () => jsonResponse(grantFor({ ...CUSTOMER, emailDeliverable: false })) })

    const user = await signIn(CUSTOMER.email, PASSWORD)

    expect(user.emailDeliverable).toBe(false)
    expect(sessionSnapshot().user?.emailDeliverable).toBe(false)
  })

  it('refuses an account that leaves the delivery flag out', async () => {
    const { emailDeliverable: _omitted, ...withoutFlag } = CUSTOMER
    mockApi({ [LOGIN_ROUTE]: () => jsonResponse({ ...grantFor(CUSTOMER), user: withoutFlag }) })

    const error = await failureOf(signIn(CUSTOMER.email, PASSWORD))

    expect(error.kind).toBe('malformed')
    expect(sessionSnapshot().user).toBeNull()
  })

  it('refuses a delivery flag that is not true or false', async () => {
    mockApi({
      [LOGIN_ROUTE]: () => jsonResponse({ ...grantFor(CUSTOMER), user: { ...CUSTOMER, emailDeliverable: 'yes' } }),
    })

    const error = await failureOf(signIn(CUSTOMER.email, PASSWORD))

    expect(error.kind).toBe('malformed')
    expect(sessionSnapshot().user).toBeNull()
  })
})
