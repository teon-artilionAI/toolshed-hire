/**
 * Tests for what the client does when a request is refused with a 401.
 *
 * I replace `fetch`, and I stand in for the session with a token I can change
 * and a renewal I can count. The real session is tested in
 * session-store.test.ts. Here the question is only the rule itself. Renew
 * once, repeat once, and share one renewal among everybody refused together.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { isApiError, malformedResponse } from '../api-problem'
import { jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import type { SeenRequest } from '../../test/api-mock'
import { bearerOf, invalidCredentials, tokenRefused } from '../../test/session-samples'
import { api } from './client'
import { registerAccessTokenProvider, registerSessionRefresher } from './session-seam'

const HELLO_ROUTE = 'GET /api/hello'
const OLD_TOKEN = 'old-token'
const NEW_TOKEN = 'new-token'

interface Greeting {
  greeting: string
}

function readGreeting(body: unknown, requestPath: string): Greeting {
  if (typeof body === 'object' && body !== null && 'greeting' in body) {
    const { greeting } = body
    if (typeof greeting === 'string') return { greeting }
  }
  throw malformedResponse(requestPath, `Expected a greeting from ${requestPath}.`)
}

/** A route that refuses the old token and welcomes the new one. */
function onlyTheNewToken(request: SeenRequest): Response {
  return bearerOf(request) === NEW_TOKEN ? jsonResponse({ greeting: 'Molo' }) : tokenRefused()
}

/**
 * Stand in for the session.
 *
 * @param outcome Whether the renewal works. When it does, the token changes.
 * @returns The renewal, so a test can count how often it was asked for.
 */
function fakeSession(outcome: 'renews' | 'cannot renew') {
  let token: string | null = OLD_TOKEN
  const refresher = vi.fn(async () => {
    // A real renewal is a request, so it finishes on a later tick.
    await Promise.resolve()
    if (outcome === 'cannot renew') {
      token = null
      return false
    }
    token = NEW_TOKEN
    return true
  })
  registerAccessTokenProvider(() => token)
  registerSessionRefresher(refresher)
  return refresher
}

async function statusOfFailure(call: Promise<unknown>): Promise<number | null> {
  try {
    await call
  } catch (thrown) {
    if (isApiError(thrown)) return thrown.status
    throw thrown
  }
  throw new Error('Expected the call to throw an ApiError, and it returned instead.')
}

afterEach(() => {
  registerAccessTokenProvider(null)
  registerSessionRefresher(null)
})

describe('a request refused for want of a good token', () => {
  it('renews the session once and is repeated once with the new token', async () => {
    const network = mockApi({ [HELLO_ROUTE]: onlyTheNewToken })
    const refresher = fakeSession('renews')

    const result = await api.get('/hello', readGreeting)

    expect(result).toEqual({ greeting: 'Molo' })
    expect(refresher).toHaveBeenCalledTimes(1)
    expect(network.requestsTo(HELLO_ROUTE).map(bearerOf)).toEqual([OLD_TOKEN, NEW_TOKEN])
  })

  it.each(['session-expired', 'authentication-failure'])(
    'is renewed when the problem type ends with %s',
    async (slug) => {
      mockApi({
        [HELLO_ROUTE]: (request) =>
          bearerOf(request) === NEW_TOKEN
            ? jsonResponse({ greeting: 'Molo' })
            : problemResponse(401, { slug }),
      })
      const refresher = fakeSession('renews')

      await api.get('/hello', readGreeting)

      expect(refresher).toHaveBeenCalledTimes(1)
    },
  )

  it('shares one renewal among requests that are refused together', async () => {
    const network = mockApi({ [HELLO_ROUTE]: onlyTheNewToken })
    const refresher = fakeSession('renews')
    // The real session shares its renewal. The stand in has to do the same for
    // this test to be about the client and not about the stand in.
    let inFlight: Promise<boolean> | null = null
    registerSessionRefresher(() => {
      inFlight ??= refresher().finally(() => {
        inFlight = null
      })
      return inFlight
    })

    const results = await Promise.all([
      api.get('/hello', readGreeting),
      api.get('/hello', readGreeting),
      api.get('/hello', readGreeting),
    ])

    expect(results).toHaveLength(3)
    expect(refresher).toHaveBeenCalledTimes(1)
    // Three refused, then each repeated exactly once.
    expect(network.requestsTo(HELLO_ROUTE)).toHaveLength(6)
  })

  it('is repeated without a second renewal when the token changed while it was out', async () => {
    let token = OLD_TOKEN
    const refresher = vi.fn(async () => true)
    registerAccessTokenProvider(() => token)
    registerSessionRefresher(refresher)
    const network = mockApi({
      [HELLO_ROUTE]: (request) => {
        // Somebody else renewed the session while this request was on its way.
        token = NEW_TOKEN
        return onlyTheNewToken(request)
      },
    })

    await api.get('/hello', readGreeting)

    expect(refresher).not.toHaveBeenCalled()
    expect(network.requestsTo(HELLO_ROUTE).map(bearerOf)).toEqual([OLD_TOKEN, NEW_TOKEN])
  })

  it('is repeated once and never twice', async () => {
    const network = mockApi({ [HELLO_ROUTE]: () => tokenRefused() })
    const refresher = fakeSession('renews')

    const status = await statusOfFailure(api.get('/hello', readGreeting))

    expect(status).toBe(401)
    expect(refresher).toHaveBeenCalledTimes(1)
    expect(network.requestsTo(HELLO_ROUTE)).toHaveLength(2)
  })

  it('fails with the refusal it got when the session cannot be renewed', async () => {
    const network = mockApi({ [HELLO_ROUTE]: onlyTheNewToken })
    const refresher = fakeSession('cannot renew')

    const status = await statusOfFailure(api.get('/hello', readGreeting))

    expect(status).toBe(401)
    expect(refresher).toHaveBeenCalledTimes(1)
    expect(network.requestsTo(HELLO_ROUTE)).toHaveLength(1)
  })
})

describe('a refusal a new token would not cure', () => {
  it('is not renewed for a 401 of another type, such as a wrong password', async () => {
    const network = mockApi({ [HELLO_ROUTE]: () => invalidCredentials() })
    const refresher = fakeSession('renews')

    const status = await statusOfFailure(api.get('/hello', readGreeting))

    expect(status).toBe(401)
    expect(refresher).not.toHaveBeenCalled()
    expect(network.requestsTo(HELLO_ROUTE)).toHaveLength(1)
  })

  it('is not renewed for a 403, which is a role and not a token', async () => {
    mockApi({ [HELLO_ROUTE]: () => problemResponse(403, { slug: 'authentication-failure' }) })
    const refresher = fakeSession('renews')

    await statusOfFailure(api.get('/hello', readGreeting))

    expect(refresher).not.toHaveBeenCalled()
  })

  it('is not renewed when the call opted out, as the session routes do', async () => {
    const network = mockApi({ 'POST /api/hello': () => tokenRefused() })
    const refresher = fakeSession('renews')

    const status = await statusOfFailure(
      api.post('/hello', undefined, readGreeting, { skipSessionRenewal: true }),
    )

    expect(status).toBe(401)
    expect(refresher).not.toHaveBeenCalled()
    expect(network.requests).toHaveLength(1)
  })

  it('is not renewed while no session is registered', async () => {
    registerAccessTokenProvider(() => OLD_TOKEN)
    registerSessionRefresher(null)
    const network = mockApi({ [HELLO_ROUTE]: () => tokenRefused() })

    const status = await statusOfFailure(api.get('/hello', readGreeting))

    expect(status).toBe(401)
    expect(network.requestsTo(HELLO_ROUTE)).toHaveLength(1)
  })
})
