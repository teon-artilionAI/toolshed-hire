import { describe, expect, it, vi } from 'vitest'

import {
  BAD_GATEWAY,
  OIDC_HEADER,
  SERVERLESS_AUTHORIZATION_HEADER,
  TOKEN_REFRESH_MARGIN_MS,
  createProxy,
  forwardedHeaders,
  settingsFrom,
  upstreamUrl,
  type ProxyDependencies,
  type ProxySettings,
} from './_proxy-core.js'

const SETTINGS: ProxySettings = {
  serviceUrl: 'https://api.example.test',
  workloadAudience: '//iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/providers/v',
  invokerAccount: 'edge@project.iam.gserviceaccount.com',
}
const NOW_MS = 1_800_000_000_000
const HOUR_MS = 60 * 60 * 1000
const SECOND_MS = 1000

function idToken(expiresAtMs: number): string {
  const part = (value: object) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${part({ alg: 'RS256' })}.${part({ exp: Math.floor(expiresAtMs / SECOND_MS) })}.signature`
}

interface Recorded {
  url: string
  init: RequestInit | undefined
}

/** A fetch that answers Google's two token calls and then the API, recording every call. */
function fakeFetch(options: { stsStatus?: number; apiResponse?: () => Response; tokenExpiresAtMs?: number } = {}) {
  const calls: Recorded[] = []
  let minted = 0
  const implementation = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    if (url.startsWith('https://sts.googleapis.com')) {
      return new Response(JSON.stringify({ access_token: 'federated' }), { status: options.stsStatus ?? 200 })
    }
    if (url.includes(':generateIdToken')) {
      minted += 1
      return new Response(JSON.stringify({ token: idToken(options.tokenExpiresAtMs ?? NOW_MS + HOUR_MS) }))
    }
    return options.apiResponse?.() ?? new Response('{"status":"healthy"}', { status: 200 })
  })
  return { implementation, calls, minted: () => minted }
}

function dependencies(fetchImplementation: typeof fetch, clock: { now: number }): ProxyDependencies {
  return { fetch: fetchImplementation, now: () => clock.now, log: vi.fn() }
}

function signedRequest(path: string, init: RequestInit = {}): Request {
  const headers = new Headers(init.headers)
  headers.set(OIDC_HEADER, 'vercel-oidc')
  return new Request(`https://site.example.test/api/proxy?__path=${path}`, { ...init, headers })
}

describe('settingsFrom', () => {
  it('names every variable that is missing', () => {
    expect(() => settingsFrom({ API_SERVICE_URL: 'https://x' })).toThrow(
      'GCP_WORKLOAD_AUDIENCE, GCP_INVOKER_ACCOUNT',
    )
  })

  it('drops a trailing slash from the service address', () => {
    const settings = settingsFrom({
      API_SERVICE_URL: 'https://api.example.test/',
      GCP_WORKLOAD_AUDIENCE: 'audience',
      GCP_INVOKER_ACCOUNT: 'account',
    })
    expect(settings.serviceUrl).toBe('https://api.example.test')
  })
})

describe('upstreamUrl', () => {
  it('puts the path back and keeps the rest of the query', () => {
    expect(upstreamUrl('https://site/api/proxy?__path=admin/reports&from=2026-01-01', 'https://api')).toBe(
      'https://api/api/admin/reports?from=2026-01-01',
    )
  })

  it('reaches the API root when the rewrite passed no path', () => {
    expect(upstreamUrl('https://site/api/proxy', 'https://api')).toBe('https://api/api/')
  })
})

describe('forwardedHeaders', () => {
  it("passes the application's own headers and drops the hop's", () => {
    const incoming = new Headers({
      authorization: 'Bearer app-token',
      cookie: 'refresh=1',
      expect: '100-continue',
      host: 'site.example.test',
      [OIDC_HEADER]: 'vercel-oidc',
      [SERVERLESS_AUTHORIZATION_HEADER]: 'Bearer forged',
    })
    const headers = forwardedHeaders(incoming, 'google-id-token')
    expect(headers.get('authorization')).toBe('Bearer app-token')
    expect(headers.get('cookie')).toBe('refresh=1')
    expect(headers.get('expect')).toBeNull()
    expect(headers.get('host')).toBeNull()
    expect(headers.get(OIDC_HEADER)).toBeNull()
    expect(headers.get(SERVERLESS_AUTHORIZATION_HEADER)).toBe('Bearer google-id-token')
  })
})

describe('createProxy', () => {
  it('forwards the request with an ID token and returns the API answer', async () => {
    const fake = fakeFetch()
    const proxy = createProxy(() => SETTINGS, dependencies(fake.implementation, { now: NOW_MS }))

    const response = await proxy(
      signedRequest('auth/login', { method: 'POST', body: '{"email":"a@b.c"}', headers: { 'content-type': 'application/json' } }),
    )

    expect(response.status).toBe(200)
    const forwarded = fake.calls.at(-1)
    expect(forwarded?.url).toBe('https://api.example.test/api/auth/login')
    expect(new Headers(forwarded?.init?.headers).get(SERVERLESS_AUTHORIZATION_HEADER)).toMatch(/^Bearer /)
    expect(new TextDecoder().decode(forwarded?.init?.body as ArrayBuffer)).toBe('{"email":"a@b.c"}')
  })

  it('mints one ID token and reuses it while it has time left', async () => {
    const fake = fakeFetch()
    const clock = { now: NOW_MS }
    const proxy = createProxy(() => SETTINGS, dependencies(fake.implementation, clock))

    await proxy(signedRequest('health'))
    clock.now += HOUR_MS / 2
    await proxy(signedRequest('health'))

    expect(fake.minted()).toBe(1)
  })

  it('mints a new ID token once the old one is inside the refresh margin', async () => {
    const fake = fakeFetch()
    const clock = { now: NOW_MS }
    const proxy = createProxy(() => SETTINGS, dependencies(fake.implementation, clock))

    await proxy(signedRequest('health'))
    clock.now = NOW_MS + HOUR_MS - TOKEN_REFRESH_MARGIN_MS + SECOND_MS
    await proxy(signedRequest('health'))

    expect(fake.minted()).toBe(2)
  })

  it('refuses a request with no Vercel OIDC token without calling Google', async () => {
    const fake = fakeFetch()
    const deps = dependencies(fake.implementation, { now: NOW_MS })
    const proxy = createProxy(() => SETTINGS, deps)

    const response = await proxy(new Request('https://site.example.test/api/proxy?__path=health'))

    expect(response.status).toBe(BAD_GATEWAY)
    expect(fake.calls).toHaveLength(0)
    expect(deps.log).toHaveBeenCalledWith('error', 'api_proxy.no_oidc_token', { method: 'GET' })
  })

  it('answers 502 and logs why when the token exchange is refused', async () => {
    const fake = fakeFetch({ stsStatus: 403 })
    const deps = dependencies(fake.implementation, { now: NOW_MS })
    const proxy = createProxy(() => SETTINGS, deps)

    const response = await proxy(signedRequest('health'))

    expect(response.status).toBe(BAD_GATEWAY)
    expect(deps.log).toHaveBeenCalledWith(
      'error',
      'api_proxy.failed',
      expect.objectContaining({ error: expect.stringContaining('The token exchange answered 403') }),
    )
  })

  it('answers 502 when the settings are missing, before any call', async () => {
    const fake = fakeFetch()
    const proxy = createProxy(() => settingsFrom({}), dependencies(fake.implementation, { now: NOW_MS }))

    const response = await proxy(signedRequest('health'))

    expect(response.status).toBe(BAD_GATEWAY)
    expect(fake.calls).toHaveLength(0)
  })

  it("passes the API's status and headers back, without the encoding fetch already undid", async () => {
    const fake = fakeFetch({
      apiResponse: () =>
        new Response('id,total\n', {
          status: 200,
          headers: { 'content-type': 'text/csv', 'content-encoding': 'gzip', 'set-cookie': 'a=1' },
        }),
    })
    const proxy = createProxy(() => SETTINGS, dependencies(fake.implementation, { now: NOW_MS }))

    const response = await proxy(signedRequest('admin/reports.csv'))

    expect(response.headers.get('content-type')).toBe('text/csv')
    expect(response.headers.get('content-encoding')).toBeNull()
    expect(response.headers.get('set-cookie')).toBe('a=1')
    expect(await response.text()).toBe('id,total\n')
  })
})
