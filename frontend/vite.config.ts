import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import type { ProxyOptions } from 'vite'

/**
 * Vite configuration.
 *
 * WHY THERE IS A PROXY HERE
 * =========================
 * The whole architecture rests on the browser seeing one origin. In production
 * the browser talks only to the Vercel domain, and Vercel rewrites `/api/*` to
 * Cloud Run server side, which is what vercel.json in this directory does. The
 * request never leaves the origin as far as the browser is concerned, so there
 * is no preflight, no CORS allow list in the request path, and the refresh
 * cookie can be `SameSite=Strict` and mean it.
 *
 * Without this block, local development would not behave that way. The page
 * would be served from http://localhost:5173 and the API would answer on
 * http://localhost:8000, which is a different origin: different port is enough.
 * Every call would become a cross origin request, the browser would preflight
 * it, and the cookie would be a third party cookie that `SameSite=Strict`
 * refuses to send. The team would then do one of two things, and both are worse
 * than this file. Either they widen CORS and loosen the cookie until it works
 * locally, and ship a weaker policy than the one the documentation claims, or
 * they point the client at an absolute `http://localhost:8000` base URL, which
 * works locally and breaks the moment it is deployed behind the rewrite.
 *
 * So the dev server carries the rewrite instead. `/api` is proxied to the local
 * uvicorn process, the page and the API share the origin `http://localhost:5173`
 * exactly as they share the Vercel origin in production, and the client can use
 * a relative `/api` base in both places. The condition the architecture exists
 * to avoid is then never entered, in either environment.
 *
 * The same block is applied to `preview`, which serves the production build.
 * A path that works under `dev` and fails under `preview` is the same class of
 * defect as one that works locally and fails in production.
 *
 * WHY THE PREVIEW SERVER SENDS HEADERS
 * ====================================
 * Vercel sends the security headers listed in vercel.json with every response,
 * and the strictest of them is the Content Security Policy. A policy is easy to
 * write and easy to get wrong, and the way it goes wrong is a blank page in
 * production that no local run ever showed.
 *
 * So `preview` sends the same headers. I read them out of vercel.json when this
 * file loads, which leaves one copy of the policy and no second list to keep in
 * step. The browser tests run against `preview`, so they load every screen
 * under the policy a visitor gets.
 *
 * The dev server does not send them. It serves the page with an inline script
 * for fast refresh and injects each stylesheet as a style element, and the
 * policy forbids both on purpose. Applying it there would only break `dev`.
 *
 * WHY FONTS ARE NEVER INLINED
 * ===========================
 * Vite writes a small asset into the bundle as a `data:` address to save a
 * request. Two subsets of the code font are small enough for that, and a font
 * loaded from `data:` is refused by `font-src 'self'`. I keep the policy and
 * change the build, so every font is written out as a file of its own.
 *
 * WHY THE POLICY HAS NO style-src-attr
 * ====================================
 * No component sets a style of its own. The bars of the chart on the
 * utilisation report are drawn as SVG, and an SVG width is an attribute of
 * its shape and not a style. Should a component ever set one through the
 * React `style` prop, React applies it through the style object of the
 * element and never writes a style attribute, and the policy governs the
 * attribute only. The browser tests load every screen under the policy, and
 * the report's download is checked there too, so the policy stays without
 * the exception.
 */

/** Where uvicorn listens locally. See backend/README.md. */
const LOCAL_API_ORIGIN = 'http://localhost:8000'

/**
 * The one path prefix the API is mounted under. It matches `API_PREFIX` in
 * `backend/app/api/routers/__init__.py` and the rewrite source in vercel.json.
 * All three must say `/api` or the single origin story breaks in one of them.
 */
const API_PATH_PREFIX = '/api'

/**
 * `changeOrigin` rewrites the Host header to the target, which is what a real
 * edge rewrite does when it forwards to a differently named upstream. Keeping
 * it true here means the backend sees the same shape of request locally as it
 * sees from Vercel, rather than a Host header that only exists in development.
 */
const API_PROXY: Record<string, ProxyOptions> = {
  [API_PATH_PREFIX]: {
    target: LOCAL_API_ORIGIN,
    changeOrigin: true,
  },
}

/** The deployment configuration this directory ships to Vercel. */
const VERCEL_CONFIG_PATH = fileURLToPath(new URL('./vercel.json', import.meta.url))

/** The `source` of the vercel.json header rule that applies to every path. */
const EVERY_PATH_SOURCE = '/(.*)'

/** Font files, which are always written out and never inlined. */
const FONT_FILE_PATTERN = /\.(woff2?|ttf|otf|eot)$/i

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Read the headers Vercel sends with every response out of vercel.json.
 *
 * @returns The header names and values of the rule whose source is every path.
 * @throws Error when vercel.json has no such rule or one of its entries is not
 *   a key and a value. I stop the build there, because a preview that quietly
 *   sent no headers would let the browser tests pass against no policy at all.
 */
function readProductionHeaders(): Record<string, string> {
  const config: unknown = JSON.parse(readFileSync(VERCEL_CONFIG_PATH, 'utf8'))
  const rules = isRecord(config) && Array.isArray(config.headers) ? config.headers : []
  const everyPath: unknown = rules.find(
    (rule: unknown) => isRecord(rule) && rule.source === EVERY_PATH_SOURCE,
  )
  if (!isRecord(everyPath) || !Array.isArray(everyPath.headers) || everyPath.headers.length === 0) {
    throw new Error(
      `Tried to read the security headers from ${VERCEL_CONFIG_PATH} and found no ` +
        `"headers" rule with the source ${EVERY_PATH_SOURCE}. Add that rule back, ` +
        'because the preview server and Vercel both take their headers from it.',
    )
  }
  const headers: Record<string, string> = {}
  for (const entry of everyPath.headers as unknown[]) {
    if (!isRecord(entry) || typeof entry.key !== 'string' || typeof entry.value !== 'string') {
      throw new Error(
        `Tried to read the security headers from ${VERCEL_CONFIG_PATH} and found an ` +
          `entry that is not a "key" and a "value" string. Got ${JSON.stringify(entry)}.`,
      )
    }
    headers[entry.key] = entry.value
  }
  return headers
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // Returning undefined leaves every other kind of asset to the default rule.
    assetsInlineLimit: (filePath) => (FONT_FILE_PATTERN.test(filePath) ? false : undefined),
  },
  server: { proxy: API_PROXY },
  preview: { proxy: API_PROXY, headers: readProductionHeaders() },
})
