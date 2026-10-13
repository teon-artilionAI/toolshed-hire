/**
 * The logic of the function that carries every `/api` request to a Cloud Run
 * service that only accepts callers with a Google identity (C-02, #96).
 *
 * The rewrite in vercel.json sent `/api` straight to the service's public
 * address, so anyone who learnt that address could skip the site. With this
 * function in front, the service requires IAM authentication and the function
 * is the only caller it lets in. No key is stored anywhere. Each request to a
 * Vercel function carries a short lived OIDC token that names the project and
 * its environment. Google's Security Token Service trusts that token through a
 * Workload Identity pool, and the federated identity may mint an ID token for
 * one invoker service account and nothing else.
 *
 * The ID token travels in `X-Serverless-Authorization`, which Cloud Run reads
 * and removes, so the application's own `Authorization` header and cookies
 * reach it unchanged. One ID token is kept for the life of the instance until
 * five minutes before it expires, so most requests make no token exchange.
 *
 * The response streams back as it arrives, which a year's CSV needs. A request
 * body is read whole first. Vercel caps a function's request body at 4.5 MB,
 * and a damage photograph is at most 4 MB.
 *
 * This file starts with an underscore so Vercel does not make it a function
 * of its own. `api/proxy.ts` is the function, and it only wires this up.
 */

const STS_URL = 'https://sts.googleapis.com/v1/token'
const IAM_CREDENTIALS_URL = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts'
const TOKEN_EXCHANGE_GRANT = 'urn:ietf:params:oauth:grant-type:token-exchange'
const JWT_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:jwt'
const ACCESS_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:access_token'
const CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
export const OIDC_HEADER = 'x-vercel-oidc-token'
export const SERVERLESS_AUTHORIZATION_HEADER = 'x-serverless-authorization'
/** The query parameter the rewrite in vercel.json puts the original path in. */
export const PATH_PARAMETER = '__path'
/** An ID token is replaced this long before it expires. */
export const TOKEN_REFRESH_MARGIN_MS = 5 * 60 * 1000
const MILLISECONDS_PER_SECOND = 1000
const LOGGED_DETAIL_CHARACTERS = 300
/**
 * Headers that describe one hop and are never passed on. Node's fetch refuses
 * a request that carries `expect`, which curl sends on any body over 1 MB.
 */
const HOP_HEADERS: ReadonlySet<string> = new Set([
  'connection',
  'keep-alive',
  'proxy-connection',
  'transfer-encoding',
  'te',
  'trailer',
  'expect',
  'upgrade',
  'host',
  'content-length',
  OIDC_HEADER,
  SERVERLESS_AUTHORIZATION_HEADER,
])
/** Response headers that no longer describe the body once fetch has decoded it. */
const DECODED_BODY_HEADERS: readonly string[] = ['content-encoding', 'content-length']
const METHODS_WITHOUT_BODY: ReadonlySet<string> = new Set(['GET', 'HEAD'])
export const BAD_GATEWAY = 502
export const UNAVAILABLE_MESSAGE = 'The API is unavailable.'

/** Where the function sends requests, and as whom. */
export interface ProxySettings {
  /** The Cloud Run service's own address, which is also the ID token's audience. */
  serviceUrl: string
  /** The Workload Identity provider, as `//iam.googleapis.com/projects/.../providers/...`. */
  workloadAudience: string
  /** The service account that holds roles/run.invoker on the service. */
  invokerAccount: string
}

/** What the proxy needs from its surroundings, so a test can supply its own. */
export interface ProxyDependencies {
  fetch: typeof fetch
  now: () => number
  log: (level: 'info' | 'error', event: string, fields: Record<string, unknown>) => void
}

interface HeldToken {
  value: string
  expiresAtMs: number
}

/**
 * Read the settings from the environment.
 *
 * @throws Error naming every missing variable, so a misconfigured deployment
 *   says what to set instead of failing on the first request it cannot route.
 */
export function settingsFrom(environment: Record<string, string | undefined>): ProxySettings {
  const required = ['API_SERVICE_URL', 'GCP_WORKLOAD_AUDIENCE', 'GCP_INVOKER_ACCOUNT'] as const
  const missing = required.filter((name) => !environment[name])
  if (missing.length > 0) {
    throw new Error(
      `The API proxy is missing ${missing.join(', ')}. Pass them to the deployment of this environment.`,
    )
  }
  return {
    serviceUrl: (environment.API_SERVICE_URL ?? '').replace(/\/$/, ''),
    workloadAudience: environment.GCP_WORKLOAD_AUDIENCE ?? '',
    invokerAccount: environment.GCP_INVOKER_ACCOUNT ?? '',
  }
}

/** Return when a JWT expires, in milliseconds since the epoch. */
export function expiryOf(jwt: string): number {
  const payload = jwt.split('.')[1] ?? ''
  const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as { exp?: unknown }
  if (typeof claims.exp !== 'number') throw new Error('The ID token from Google carries no expiry.')
  return claims.exp * MILLISECONDS_PER_SECOND
}

/** The service's address for an incoming request, with the rewrite's path parameter removed. */
export function upstreamUrl(requestUrl: string, serviceUrl: string): string {
  const incoming = new URL(requestUrl)
  const path = incoming.searchParams.get(PATH_PARAMETER) ?? ''
  incoming.searchParams.delete(PATH_PARAMETER)
  const query = incoming.searchParams.toString()
  return `${serviceUrl}/api/${path}${query ? `?${query}` : ''}`
}

/** The incoming headers without the hop's own, and with the ID token for Cloud Run. */
export function forwardedHeaders(incoming: Headers, idToken: string): Headers {
  const headers = new Headers()
  incoming.forEach((value, name) => {
    if (!HOP_HEADERS.has(name.toLowerCase())) headers.append(name, value)
  })
  headers.set(SERVERLESS_AUTHORIZATION_HEADER, `Bearer ${idToken}`)
  return headers
}

async function failure(step: string, response: Response): Promise<Error> {
  const detail = (await response.text()).slice(0, LOGGED_DETAIL_CHARACTERS)
  return new Error(`${step} answered ${response.status}: ${detail}`)
}

/** Build the request handler. It holds one ID token for as long as the instance lives. */
export function createProxy(
  settings: () => ProxySettings,
  dependencies: ProxyDependencies,
): (request: Request) => Promise<Response> {
  let held: HeldToken | undefined

  async function idTokenFor(vercelToken: string, config: ProxySettings): Promise<string> {
    if (held && held.expiresAtMs - TOKEN_REFRESH_MARGIN_MS > dependencies.now()) return held.value
    const started = dependencies.now()
    const exchange = await dependencies.fetch(STS_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        grantType: TOKEN_EXCHANGE_GRANT,
        audience: config.workloadAudience,
        scope: CLOUD_PLATFORM_SCOPE,
        requestedTokenType: ACCESS_TOKEN_TYPE,
        subjectToken: vercelToken,
        subjectTokenType: JWT_TOKEN_TYPE,
      }),
    })
    if (!exchange.ok) throw await failure('The token exchange', exchange)
    const { access_token: federatedToken } = (await exchange.json()) as { access_token: string }

    const minting = await dependencies.fetch(
      `${IAM_CREDENTIALS_URL}/${config.invokerAccount}:generateIdToken`,
      {
        method: 'POST',
        headers: { authorization: `Bearer ${federatedToken}`, 'content-type': 'application/json' },
        body: JSON.stringify({ audience: config.serviceUrl, includeEmail: true }),
      },
    )
    if (!minting.ok) throw await failure('Minting the ID token', minting)
    const { token } = (await minting.json()) as { token: string }
    held = { value: token, expiresAtMs: expiryOf(token) }
    dependencies.log('info', 'api_proxy.token_minted', { took_ms: dependencies.now() - started })
    return token
  }

  return async function proxy(request: Request): Promise<Response> {
    const vercelToken = request.headers.get(OIDC_HEADER)
    if (!vercelToken) {
      dependencies.log('error', 'api_proxy.no_oidc_token', { method: request.method })
      return new Response(UNAVAILABLE_MESSAGE, { status: BAD_GATEWAY })
    }
    try {
      const config = settings()
      const idToken = await idTokenFor(vercelToken, config)
      const body = METHODS_WITHOUT_BODY.has(request.method) ? undefined : await request.arrayBuffer()
      const upstream = await dependencies.fetch(upstreamUrl(request.url, config.serviceUrl), {
        method: request.method,
        headers: forwardedHeaders(request.headers, idToken),
        body,
        redirect: 'manual',
      })
      const headers = new Headers(upstream.headers)
      for (const name of DECODED_BODY_HEADERS) headers.delete(name)
      return new Response(upstream.body, { status: upstream.status, headers })
    } catch (error) {
      dependencies.log('error', 'api_proxy.failed', { method: request.method, error: String(error) })
      return new Response(UNAVAILABLE_MESSAGE, { status: BAD_GATEWAY })
    }
  }
}
