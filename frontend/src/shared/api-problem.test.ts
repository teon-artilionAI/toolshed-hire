/**
 * Tests for the failure half of the API client.
 *
 * Each test hands the module a response the way the network would deliver it
 * and checks the `ApiError` a screen would receive. The cases follow the three
 * things that can go wrong. The API says no in the documented format, the edge
 * in front of the API cannot reach it, or something answers in a shape the
 * contract never promised.
 */

import { describe, expect, it } from 'vitest'
import {
  ApiError,
  asApiError,
  errorFromResponse,
  isApiError,
  parseJsonBody,
  requireField,
} from './api-problem'

const REQUEST_PATH = '/api/reservations'
const PROBLEM_JSON = 'application/problem+json'

function responseWith(status: number, statusText: string, contentType?: string): Response {
  const headers = new Headers()
  if (contentType) headers.set('content-type', contentType)
  return new Response(null, { status, statusText, headers })
}

describe('a problem+json response', () => {
  const body = JSON.stringify({
    type: 'https://toolshedhire.example/problems/unit-already-booked',
    title: 'That unit has just been booked',
    status: 409,
    detail: 'Somebody else confirmed the same unit for an overlapping period.',
    instance: '/api/reservations/42',
    errors: { unitId: 'already allocated' },
  })

  it('becomes an ApiError that speaks in the words the server chose', () => {
    const error = errorFromResponse(responseWith(409, 'Conflict', PROBLEM_JSON), body, REQUEST_PATH)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.kind).toBe('problem')
    expect(error.status).toBe(409)
    expect(error.title).toBe('That unit has just been booked')
    expect(error.detail).toBe('Somebody else confirmed the same unit for an overlapping period.')
    expect(error.requestPath).toBe(REQUEST_PATH)
    expect(error.isBackendUnreachable).toBe(false)
  })

  it('keeps the whole problem document for a screen that needs the field errors', () => {
    const error = errorFromResponse(responseWith(409, 'Conflict', PROBLEM_JSON), body, REQUEST_PATH)

    expect(error.problem).toEqual({
      type: 'https://toolshedhire.example/problems/unit-already-booked',
      title: 'That unit has just been booked',
      status: 409,
      detail: 'Somebody else confirmed the same unit for an overlapping period.',
      instance: '/api/reservations/42',
      errors: { unitId: 'already allocated' },
    })
  })

  it('is still recognised when the content type carries a charset', () => {
    const response = responseWith(409, 'Conflict', `${PROBLEM_JSON}; charset=utf-8`)

    expect(errorFromResponse(response, body, REQUEST_PATH).title).toBe(
      'That unit has just been booked',
    )
  })

  it('fills the optional members from the response when the document leaves them out', () => {
    const sparse = JSON.stringify({ detail: 'The email address is already registered.' })
    const error = errorFromResponse(responseWith(422, 'Unprocessable Entity', PROBLEM_JSON), sparse, REQUEST_PATH)

    expect(error.detail).toBe('The email address is already registered.')
    expect(error.title).toBe('Unprocessable Entity')
    expect(error.problem?.type).toBe('about:blank')
    expect(error.problem?.status).toBe(422)
  })
})

describe('a gateway failure', () => {
  it.each([502, 503, 504])('reports an empty %i as the API being unreachable', (status) => {
    const error = errorFromResponse(responseWith(status, ''), '', '/api/health')

    expect(error.kind).toBe('gateway')
    expect(error.status).toBe(status)
    expect(error.isBackendUnreachable).toBe(true)
    expect(error.problem).toBeNull()
    expect(error.detail).toContain('/api/health')
  })

  it('treats an HTML error page from the proxy the same way', () => {
    const html = '<html><body><h1>502 Bad Gateway</h1></body></html>'
    const error = errorFromResponse(responseWith(502, 'Bad Gateway', 'text/html'), html, '/api/health')

    expect(error.kind).toBe('gateway')
    expect(error.isBackendUnreachable).toBe(true)
  })

  it('does not mistake a 503 health report for a gateway failure', () => {
    // The API answers 503 itself when a dependency is down. That is the API
    // speaking, so the backend was reached.
    const report = JSON.stringify({ status: 'unavailable', database: 'down' })
    const error = errorFromResponse(responseWith(503, 'Service Unavailable', 'application/json'), report, '/api/health')

    expect(error.kind).toBe('problem')
    expect(error.status).toBe(503)
    expect(error.isBackendUnreachable).toBe(false)
  })
})

describe('a malformed body', () => {
  it('on a failed response is reported by status, saying the document was missing', () => {
    const error = errorFromResponse(responseWith(500, 'Internal Server Error', 'text/plain'), 'Traceback (most recent call last)', REQUEST_PATH)

    expect(error.kind).toBe('problem')
    expect(error.status).toBe(500)
    expect(error.title).toBe('Internal Server Error')
    expect(error.detail).toContain('without a problem document')
    expect(error.problem).toBeNull()
  })

  it('on a failed response that claims problem+json but is cut short is not trusted', () => {
    const truncated = '{"title": "Conflict", "detail": "Somebody else'
    const error = errorFromResponse(responseWith(409, 'Conflict', PROBLEM_JSON), truncated, REQUEST_PATH)

    expect(error.status).toBe(409)
    expect(error.problem).toBeNull()
    expect(error.detail).toContain('without a problem document')
  })

  it('names the status when the response has no status text', () => {
    const error = errorFromResponse(responseWith(500, ''), 'not json', REQUEST_PATH)

    expect(error.title).toBe('HTTP 500')
  })

  it('on a successful response throws a malformed error that quotes what arrived', () => {
    const thrown = captureError(() => parseJsonBody('definitely not json', 200, REQUEST_PATH))

    expect(thrown.kind).toBe('malformed')
    expect(thrown.status).toBe(200)
    expect(thrown.detail).toContain('definitely not json')
    expect(thrown.isBackendUnreachable).toBe(false)
  })

  it('points at the proxy when the body is the single page application', () => {
    const thrown = captureError(() => parseJsonBody('<!doctype html><html></html>', 200, '/api/health'))

    expect(thrown.kind).toBe('malformed')
    expect(thrown.detail).toContain('returned HTML')
    expect(thrown.detail).toContain('vite.config.ts')
  })

  it('throws a malformed error naming a field that is missing', () => {
    const thrown = captureError(() => requireField<string>({}, 'accessToken', 'string', '/api/auth/sign-in'))

    expect(thrown.kind).toBe('malformed')
    expect(thrown.detail).toContain('accessToken')
    expect(thrown.detail).toContain('/api/auth/sign-in')
  })

  it('throws a malformed error for a field of the wrong type', () => {
    const thrown = captureError(() => requireField<string>({ accessToken: 12 }, 'accessToken', 'string', '/api/auth/sign-in'))

    expect(thrown.detail).toContain('got number')
  })
})

describe('a well formed body', () => {
  it('is returned as parsed JSON', () => {
    expect(parseJsonBody('{"status":"ok"}', 200, '/api/health')).toEqual({ status: 'ok' })
  })

  it('is null for a 204, which has no body to read', () => {
    expect(parseJsonBody('', 204, REQUEST_PATH)).toBeNull()
  })

  it('gives back a required field of the right type', () => {
    expect(requireField<string>({ accessToken: 'abc' }, 'accessToken', 'string', '/api/auth/sign-in')).toBe('abc')
  })
})

describe('a failure that was never an API response', () => {
  it('is wrapped as unexpected and keeps the original as its cause', () => {
    const original = new TypeError('Failed to fetch')
    const error = asApiError(original, REQUEST_PATH)

    expect(error.kind).toBe('unexpected')
    expect(error.status).toBeNull()
    expect(error.cause).toBe(original)
    expect(error.detail).toContain('Failed to fetch')
  })

  it('passes an existing ApiError through untouched', () => {
    const original = errorFromResponse(responseWith(502, ''), '', REQUEST_PATH)

    expect(asApiError(original, REQUEST_PATH)).toBe(original)
  })
})

/** Run something that must throw an ApiError and hand the error back. */
function captureError(run: () => unknown): ApiError {
  try {
    run()
  } catch (thrown) {
    if (isApiError(thrown)) return thrown
    throw thrown
  }
  throw new Error('Expected the call to throw an ApiError, and it returned instead.')
}
