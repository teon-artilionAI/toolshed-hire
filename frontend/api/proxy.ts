/**
 * The function that carries every `/api` request to the Cloud Run service
 * when the service accepts only callers with a Google identity (C-02, #96).
 *
 * The rewrite in vercel.json sends `/api/...` here with the original path in
 * a query parameter. Everything this does is in `_proxy-core.ts`, which
 * explains the token exchange. Logs are one JSON object per line, which
 * Vercel's runtime log keeps as written.
 */

import { createProxy, settingsFrom } from './_proxy-core.js'

const proxy = createProxy(() => settingsFrom(process.env), {
  fetch: (input, init) => fetch(input, init),
  now: () => Date.now(),
  log: (level, event, fields) => {
    const line = JSON.stringify({ level, event, ...fields })
    if (level === 'error') console.error(line)
    else console.info(line)
  },
})

export const GET = proxy
export const HEAD = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const OPTIONS = proxy
