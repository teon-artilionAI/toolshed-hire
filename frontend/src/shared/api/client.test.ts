/**
 * Tests for the HTTP client.
 *
 * I replace `fetch` and nothing else, then check two things. What the client
 * put on the wire, and what a caller got back. The reader each call passes is
 * a real one, so a test also proves the body reached it.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { isApiError, malformedResponse } from '../api-problem'
import type { ApiError } from '../api-problem'
import { jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import { REQUEST_TIMEOUT_MS, api, apiPath, registerAccessTokenProvider } from './client'

interface Greeting {
  greeting: string
}

/** A reader that accepts `{ greeting: string }` and refuses anything else. */
function readGreeting(body: unknown, requestPath: string): Greeting {
  if (typeof body === 'object' && body !== null && 'greeting' in body) {
    const { greeting } = body
    if (typeof greeting === 'string') return { greeting }
  }
  throw malformedResponse(requestPath, `Expected a greeting from ${requestPath}.`)
}

/** Run a call that must fail and hand back the ApiError it threw. */
async function failureOf(call: Promise<unknown>): Promise<ApiError> {
  try {
    await call
  } catch (thrown) {
    if (isApiError(thrown)) return thrown
    throw thrown
  }
  throw new Error('Expected the call to throw an ApiError, and it returned instead.')
}

/** A server that never answers, and gives up only when the request is aborted. */
function stalledUntilAborted(signal: AbortSignal | null): Promise<Response> {
  return new Promise<Response>((_resolve, reject) => {
    signal?.addEventListener('abort', () =>
      reject(new DOMException('The operation was aborted.', 'AbortError')),
    )
  })
}

afterEach(() => {
  registerAccessTokenProvider(null)
})

describe('the base path', () => {
  it('is relative, so every call stays on the page origin', () => {
    expect(apiPath('/branches')).toBe('/api/branches')
  })
})

describe('GET', () => {
  it('asks the relative path with the query string and returns the body it read', async () => {
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })

    const result = await api.get('/hello', readGreeting, { query: { name: 'Thandi', page: 1 } })

    expect(result).toEqual({ greeting: 'Molo' })
    const [request] = network.requests
    expect(request.method).toBe('GET')
    expect(request.path).toBe('/api/hello')
    expect(request.query.get('name')).toBe('Thandi')
    expect(request.query.get('page')).toBe('1')
    expect(request.body).toBeUndefined()
  })

  it('sends cookies and asks for JSON', async () => {
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })

    await api.get('/hello', readGreeting)

    expect(network.requests[0].credentials).toBe('include')
    expect(network.requests[0].headers.get('Accept')).toBe('application/json')
    expect(network.requests[0].headers.has('Content-Type')).toBe(false)
  })

  it('returns the body of a status the caller said carries an answer', async () => {
    mockApi({
      'GET /api/hello': () =>
        new Response(JSON.stringify({ greeting: 'Degraded' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
    })

    await expect(api.get('/hello', readGreeting, { bodyBearingStatuses: [503] })).resolves.toEqual({
      greeting: 'Degraded',
    })
  })
})

describe.each([
  ['POST', api.post],
  ['PUT', api.put],
  ['PATCH', api.patch],
] as const)('%s', (method, send) => {
  it('sends the body as JSON and returns what it read', async () => {
    const network = mockApi({ [`${method} /api/hello`]: () => jsonResponse({ greeting: 'Saved' }) })

    const result = await send('/hello', { name: 'Thandi', quantity: 2 }, readGreeting)

    expect(result).toEqual({ greeting: 'Saved' })
    const [request] = network.requests
    expect(request.method).toBe(method)
    expect(request.body).toEqual({ name: 'Thandi', quantity: 2 })
    expect(request.headers.get('Content-Type')).toBe('application/json')
    expect(request.credentials).toBe('include')
  })
})

describe('the verbs on offer', () => {
  it('do not include DELETE, because this system never deletes a record', () => {
    expect(Object.keys(api).sort()).toEqual(['get', 'patch', 'post', 'put'])
  })
})

describe('the bearer token', () => {
  it('is not sent while no provider is registered', async () => {
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })

    await api.get('/hello', readGreeting)

    expect(network.requests[0].headers.has('Authorization')).toBe(false)
  })

  it('comes from the registered provider, asked afresh on every request', async () => {
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })
    let token: string | null = 'first-token'
    registerAccessTokenProvider(() => token)

    await api.get('/hello', readGreeting)
    token = 'second-token'
    await api.get('/hello', readGreeting)
    token = null
    await api.get('/hello', readGreeting)

    expect(network.requests[0].headers.get('Authorization')).toBe('Bearer first-token')
    expect(network.requests[1].headers.get('Authorization')).toBe('Bearer second-token')
    expect(network.requests[2].headers.has('Authorization')).toBe(false)
  })

  it('stops being sent once the provider is taken away', async () => {
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })
    registerAccessTokenProvider(() => 'session-token')
    registerAccessTokenProvider(null)

    await api.get('/hello', readGreeting)

    expect(network.requests[0].headers.has('Authorization')).toBe(false)
  })
})

describe('a failed call', () => {
  it('becomes an ApiError carrying the status, the words and the request id', async () => {
    mockApi({
      'GET /api/hello': () =>
        problemResponse(409, {
          detail: 'Somebody else booked that unit.',
          requestId: 'req-from-document',
        }),
    })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.kind).toBe('problem')
    expect(error.status).toBe(409)
    expect(error.detail).toBe('Somebody else booked that unit.')
    expect(error.requestPath).toBe('/api/hello')
    expect(error.requestId).toBe('req-from-document')
    expect(error.problem?.requestId).toBe('req-from-document')
  })

  it('keeps the field errors of a 422 on the problem document', async () => {
    mockApi({
      'GET /api/hello': () => problemResponse(422, { errors: { from: 'Must be today or later.' } }),
    })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.status).toBe(422)
    expect(error.problem?.errors).toEqual({ from: 'Must be today or later.' })
  })

  it('takes the request id from the header when the body has none', async () => {
    mockApi({
      'GET /api/hello': () =>
        new Response('Internal Server Error', {
          status: 500,
          statusText: 'Internal Server Error',
          headers: { 'X-Request-ID': 'req-from-header' },
        }),
    })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.status).toBe(500)
    expect(error.requestId).toBe('req-from-header')
  })

  it('reports an empty 502 as the API being unreachable', async () => {
    mockApi({ 'GET /api/hello': () => new Response('', { status: 502 }) })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.kind).toBe('gateway')
    expect(error.isBackendUnreachable).toBe(true)
    expect(error.requestId).toBeNull()
  })

  it('reports a request that never reached a server as a transport failure', async () => {
    mockApi({
      'GET /api/hello': () => {
        throw new TypeError('Failed to fetch')
      },
    })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.kind).toBe('transport')
    expect(error.status).toBeNull()
    expect(error.isBackendUnreachable).toBe(true)
    expect(error.title).toBe('The API could not be reached')
  })

  it('reports a body the reader refuses as malformed, with the request id', async () => {
    mockApi({ 'GET /api/hello': () => jsonResponse({ salutation: 'Molo' }, 'req-odd-shape') })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.kind).toBe('malformed')
    expect(error.requestId).toBe('req-odd-shape')
  })

  it('reports a body that is not JSON as malformed', async () => {
    mockApi({
      'GET /api/hello': () => new Response('<!doctype html><html></html>', { status: 200 }),
    })

    const error = await failureOf(api.get('/hello', readGreeting))

    expect(error.kind).toBe('malformed')
    expect(error.detail).toContain('returned HTML')
  })
})

describe('the timeout', () => {
  it('abandons a request the server never answers and says it timed out', async () => {
    vi.useFakeTimers()
    const network = mockApi({ 'GET /api/hello': ({ signal }) => stalledUntilAborted(signal) })

    const pending = failureOf(api.get('/hello', readGreeting))
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS - 1)
    expect(network.requests[0].signal?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    const error = await pending

    expect(network.requests[0].signal?.aborted).toBe(true)
    expect(error.kind).toBe('transport')
    expect(error.title).toBe('The API did not answer in time')
    expect(error.detail).toContain(String(REQUEST_TIMEOUT_MS))
  })

  it('does not fire once a request has been answered', async () => {
    vi.useFakeTimers()
    const network = mockApi({ 'GET /api/hello': () => jsonResponse({ greeting: 'Molo' }) })

    await api.get('/hello', readGreeting)
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS * 2)

    expect(network.requests[0].signal?.aborted).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('a request the caller abandons', () => {
  it('is stopped, and is not reported as a failure of the API', async () => {
    const network = mockApi({ 'GET /api/hello': ({ signal }) => stalledUntilAborted(signal) })
    const caller = new AbortController()

    const pending = api.get('/hello', readGreeting, { signal: caller.signal })
    caller.abort()

    await expect(pending).rejects.toSatisfy(
      (thrown: unknown) =>
        !isApiError(thrown) && thrown instanceof DOMException && thrown.name === 'AbortError',
    )
    expect(network.requests[0].signal?.aborted).toBe(true)
  })
})
