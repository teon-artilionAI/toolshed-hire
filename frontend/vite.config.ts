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

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy: API_PROXY },
  preview: { proxy: API_PROXY },
})
