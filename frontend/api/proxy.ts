/// <reference types="node" />
/**
 * The function that carries every `/api` request to a Cloud Run service that
 * only accepts callers with a Google identity (C-02, #109).
 *
 * The rewrite in vercel.json used to send `/api` straight to the service's
 * public address, so anyone who learnt that address could skip the site. Here
 * the service requires IAM authentication, and this function is the only
 * caller it lets in. No key is stored anywhere. Each request to a Vercel
 * function carries a short lived OIDC token that names this project and its
 * environment. Google's Security Token Service trusts that token through a
 * Workload Identity pool, and the federated identity may mint an ID token for
 * one invoker service account and nothing else.
 *
 * The ID token travels in `X-Serverless-Authorization`, which Cloud Run reads
 * and removes, so the application's own `Authorization` header and cookies
 * reach it unchanged. The ID token is kept for the life of this instance until
 * five minutes before it expires, so most requests cost no token exchange.
 *
 * The response streams back as it arrives, which a year's CSV needs. A request
 * body is read whole first. Vercel caps a function's request body at 4.5 MB,
 * and a damage photograph is at most 4 MB.
 */

const STS_URL = 'https://sts.googleapis.com/v1/token'
const TOKEN_EXCHANGE_GRANT = 'urn:ietf:params:oauth:grant-type:token-exchange'
const JWT_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:jwt'
const ACCESS_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:access_token'
const CLOUD_PLATFORM_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'
const OIDC_HEADER = 'x-vercel-oidc-token'
const SERVERLESS_AUTHORIZATION_HEADER = 'x-serverless-authorization'
/** The query parameter the rewrite in vercel.json puts the original path in. */
const PATH_PARAMETER = '__path'
/** An ID token is replaced this long before it expires. */
const TOKEN_REFRESH_MARGIN_MS = 5 * 60 * 1000
const MILLISECONDS_PER_SECOND = 1000
/**
 * Headers that describe one hop and are never passed on. Node's fetch refuses
 * a request that carries `expect`, which curl sends on any body over 1 MB.
 */
const HOP_HEADERS = new Set([
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
const METHODS_WITHOUT_BODY = new Set(['GET', 'HEAD'])
const BAD_GATEWAY = 502

interface ProxySettings {
  serviceUrl: string
  workloadAudience: string
  invokerAccount: string
}

interface CachedToken {
  value: string
  expiresAtMs: number
}

let cachedToken: CachedToken | undefined

function settings(): ProxySettings {
  const serviceUrl = process.env.API_SERVICE_URL
  const workloadAudience = process.env.GCP_WORKLOAD_AUDIENCE
  const invokerAccount = process.env.GCP_INVOKER_ACCOUNT
  if (!serviceUrl || !workloadAudience || !invokerAccount) {
    throw new Error(
      'The API proxy needs API_SERVICE_URL, GCP_WORKLOAD_AUDIENCE and GCP_INVOKER_ACCOUNT. ' +
        'Set them on the Vercel project for this environment.',
    )
  }
  return { serviceUrl: serviceUrl.replace(/\/$/, ''), workloadAudience, invokerAccount }
}

function expiryOf(idToken: string): number {
  const payload = idToken.split('.')[1] ?? ''
  const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as { exp?: number }
  if (typeof claims.exp !== 'number') throw new Error('The ID token from Google carries no expiry.')
  return claims.exp * MILLISECONDS_PER_SECOND
}

async function failure(step: string, response: Response): Promise<Error> {
  const detail = (await response.text()).slice(0, 300)
  return new Error(`${step} answered ${response.status}: ${detail}`)
}

/** Return an ID token for the service, exchanging the Vercel OIDC token when none is held. */
async function idTokenFor(vercelToken: string, config: ProxySettings): Promise<string> {
  if (cachedToken && cachedToken.expiresAtMs - TOKEN_REFRESH_MARGIN_MS > Date.now()) {
    return cachedToken.value
  }
  const started = Date.now()
  const exchange = await fetch(STS_URL, {
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

  const minting = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${config.invokerAccount}:generateIdToken`,
    {
      method: 'POST',
      headers: { authorization: `Bearer ${federatedToken}`, 'content-type': 'application/json' },
      body: JSON.stringify({ audience: config.serviceUrl, includeEmail: true }),
    },
  )
  if (!minting.ok) throw await failure('Minting the ID token', minting)
  const { token } = (await minting.json()) as { token: string }
  cachedToken = { value: token, expiresAtMs: expiryOf(token) }
  console.info(JSON.stringify({ event: 'api_proxy.token_minted', took_ms: Date.now() - started }))
  return token
}

function upstreamUrl(request: Request, serviceUrl: string): string {
  const incoming = new URL(request.url)
  const path = incoming.searchParams.get(PATH_PARAMETER) ?? ''
  incoming.searchParams.delete(PATH_PARAMETER)
  const query = incoming.searchParams.toString()
  return `${serviceUrl}/api/${path}${query ? `?${query}` : ''}`
}

function forwardedHeaders(request: Request, idToken: string): Headers {
  const headers = new Headers()
  request.headers.forEach((value, name) => {
    if (!HOP_HEADERS.has(name.toLowerCase())) headers.set(name, value)
  })
  headers.set(SERVERLESS_AUTHORIZATION_HEADER, `Bearer ${idToken}`)
  return headers
}

async function proxy(request: Request): Promise<Response> {
  const vercelToken = request.headers.get(OIDC_HEADER)
  if (!vercelToken) {
    console.error(JSON.stringify({ event: 'api_proxy.no_oidc_token' }))
    return new Response('The API is unavailable.', { status: BAD_GATEWAY })
  }
  try {
    const config = settings()
    const idToken = await idTokenFor(vercelToken, config)
    const body = METHODS_WITHOUT_BODY.has(request.method) ? undefined : await request.arrayBuffer()
    const upstream = await fetch(upstreamUrl(request, config.serviceUrl), {
      method: request.method,
      headers: forwardedHeaders(request, idToken),
      body,
      redirect: 'manual',
    })
    const headers = new Headers(upstream.headers)
    headers.delete('content-encoding')
    headers.delete('content-length')
    return new Response(upstream.body, { status: upstream.status, headers })
  } catch (error) {
    console.error(
      JSON.stringify({ event: 'api_proxy.failed', method: request.method, error: String(error) }),
    )
    return new Response('The API is unavailable.', { status: BAD_GATEWAY })
  }
}

export const GET = proxy
export const HEAD = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const OPTIONS = proxy
