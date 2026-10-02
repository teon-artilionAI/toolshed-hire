/**
 * A stand-in for the network, for tests.
 *
 * I replace `fetch` itself and nothing above it, so a test exercises the real
 * client, the real cache and the real screen. Each test says how each route
 * answers and then looks at the page the way a person would.
 *
 * A request for a route the test did not set up is answered with a 501 that
 * names the route. It is not retried, so the test fails quickly and the page
 * says which answer was missing.
 */

import { vi } from 'vitest'
import type { Mock } from 'vitest'

const PROBLEM_MEDIA_TYPE = 'application/problem+json'
const REQUEST_ID_HEADER = 'X-Request-ID'
const HTTP_NOT_IMPLEMENTED = 501
const HTTP_NO_CONTENT = 204
/** What every problem `type` the API sends starts with. */
const PROBLEM_TYPE_PREFIX = 'https://toolshedhire.co.za/problems/'

/** One request as a test sees it. */
export interface SeenRequest {
  method: string
  /** The path without the query string, for example `/api/branches`. */
  path: string
  query: URLSearchParams
  headers: Headers
  /** The parsed JSON body, or undefined when the request had none. */
  body: unknown
  credentials: RequestCredentials | undefined
  signal: AbortSignal | null
}

export type RouteHandler = (request: SeenRequest) => Response | Promise<Response>

/** Routes keyed by method and path, for example `GET /api/branches`. */
export type RouteTable = Record<string, RouteHandler>

export interface ApiMock {
  /** The replaced `fetch`, for a test that wants to count calls. */
  fetch: Mock
  /** Every request made so far, oldest first. */
  requests: SeenRequest[]
  /** The requests made to one route. */
  requestsTo: (route: string) => SeenRequest[]
  /** Change how a route answers from now on. */
  setRoute: (route: string, handler: RouteHandler) => void
}

/** A 200 with a JSON body, the way the API sends one. */
export function jsonResponse(body: unknown, requestId = 'req-test-0001'): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', [REQUEST_ID_HEADER]: requestId },
  })
}

/** A 204 with no body, which is how the API answers a sign out. */
export function noContentResponse(requestId = 'req-test-0204'): Response {
  return new Response(null, { status: HTTP_NO_CONTENT, headers: { [REQUEST_ID_HEADER]: requestId } })
}

/** A problem document, the way the API sends every error. */
export function problemResponse(
  status: number,
  options: {
    detail?: string
    errors?: Record<string, unknown>
    requestId?: string
    /** How the `type` ends, for example `session-expired`. */
    slug?: string
    /** Further response headers, for example `Retry-After`. */
    headers?: Record<string, string>
  } = {},
): Response {
  const requestId = options.requestId ?? 'req-test-problem'
  return new Response(
    JSON.stringify({
      type: `${PROBLEM_TYPE_PREFIX}${options.slug ?? 'test'}`,
      title: 'Test Problem',
      status,
      detail: options.detail ?? 'The request could not be completed.',
      requestId,
      ...(options.errors ? { errors: options.errors } : {}),
    }),
    {
      status,
      headers: {
        'Content-Type': PROBLEM_MEDIA_TYPE,
        [REQUEST_ID_HEADER]: requestId,
        ...options.headers,
      },
    },
  )
}

/** A promise that never settles, for a test that looks at the loading state. */
export function neverAnswers(): Promise<Response> {
  return new Promise<Response>(() => {})
}

function seenRequest(input: RequestInfo | URL, init: RequestInit | undefined): SeenRequest {
  const url = new URL(String(input), 'http://localhost')
  return {
    method: init?.method ?? 'GET',
    path: url.pathname,
    query: url.searchParams,
    headers: new Headers(init?.headers),
    body: typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined,
    credentials: init?.credentials,
    signal: init?.signal ?? null,
  }
}

/**
 * Replace `fetch` with a table of routes for the rest of the test.
 *
 * The setup file puts the real `fetch` back after each test.
 */
export function mockApi(routes: RouteTable): ApiMock {
  const table: RouteTable = { ...routes }
  const requests: SeenRequest[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = seenRequest(input, init)
    requests.push(request)
    const route = `${request.method} ${request.path}`
    const handler = table[route]
    if (!handler) {
      return problemResponse(HTTP_NOT_IMPLEMENTED, {
        detail: `The test set up no answer for ${route}.`,
      })
    }
    return handler(request)
  })
  vi.stubGlobal('fetch', fetchMock)
  return {
    fetch: fetchMock,
    requests,
    requestsTo: (route) =>
      requests.filter((request) => `${request.method} ${request.path}` === route),
    setRoute: (route, handler) => {
      table[route] = handler
    },
  }
}
