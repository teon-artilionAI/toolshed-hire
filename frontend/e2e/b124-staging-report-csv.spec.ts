/**
 * B12.4 stage 2, the owner's full-year report CSV on staging.
 *
 * The report screen already reads the figures. This journey signs the owner in
 * through the protected staging runner, exchanges the refresh cookie for an
 * access token, and reads the full-year CSV through the deployed `/api`
 * function. It checks the comment line, the column line, the row count, the
 * attachment name and the time to the first chunk and to the end.
 *
 * It only reads. It creates no booking, charge or report.
 */

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { signInAsOwner } from './staff.ts'
import { note, onStaging } from './staging.ts'

const FROM = '2026-01-01'
const TO = '2027-01-01'
const CSV_PATH = `/api/admin/reports/utilisation.csv?from=${FROM}&to=${TO}&groupBy=model`
const TIME_LIMIT_MS = 10_000

interface Session {
  headers: { Authorization: string }
  token: string
}

interface StreamResult {
  status: number
  contentType: string | null
  disposition: string | null
  firstLine: string
  headerLine: string
  lineCount: number
  bytes: number
  chunks: number
  firstChunkMs: number
  totalMs: number
}

async function session(request: APIRequestContext): Promise<Session> {
  const response = await request.post('/api/auth/refresh')
  if (!response.ok()) {
    throw new Error(`POST /api/auth/refresh returned ${response.status()}: ${await response.text()}`)
  }
  const body = (await response.json()) as { accessToken?: string }
  if (body.accessToken === undefined || body.accessToken === '') {
    throw new Error('The refresh answer carried no access token.')
  }
  return {
    headers: { Authorization: `Bearer ${body.accessToken}` },
    token: body.accessToken,
  }
}

test('the owner reads the full-year report CSV through the staging function', { tag: '@staging' }, async ({
  page,
  request,
}) => {
  test.skip(!onStaging(), 'This report check runs on the staging project only.')

  const health = await request.get('/api/health')
  expect(health.ok()).toBe(true)
  const healthBody = (await health.json()) as {
    environment: string
    revision: string
    databaseReachable: boolean
  }
  expect(healthBody.environment).toBe('staging')
  expect(healthBody.databaseReachable).toBe(true)
  expect(healthBody.revision).toMatch(/^toolshed-api-staging-/)

  await signInAsOwner(page)
  const owner = await session(page.request)
  const result = (await page.evaluate(
    async ({ path, token }) => {
      const started = performance.now()
      const response = await fetch(path, { headers: { Authorization: `Bearer ${token}` } })
      const body = response.body
      if (body === null) {
        return {
          status: response.status,
          contentType: response.headers.get('content-type'),
          disposition: response.headers.get('content-disposition'),
          firstLine: '',
          headerLine: '',
          lineCount: 0,
          bytes: 0,
          chunks: 0,
          firstChunkMs: 0,
          totalMs: performance.now() - started,
        }
      }
      const reader = body.getReader()
      const decoder = new TextDecoder()
      let text = ''
      let bytes = 0
      let chunks = 0
      let firstChunkMs = 0
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        if (chunks === 0) firstChunkMs = performance.now() - started
        chunks += 1
        bytes += value.byteLength
        text += decoder.decode(value, { stream: true })
      }
      text += decoder.decode()
      const lines = text.split(/\r?\n/).filter((line) => line.length > 0)
      return {
        status: response.status,
        contentType: response.headers.get('content-type'),
        disposition: response.headers.get('content-disposition'),
        firstLine: lines[0] ?? '',
        headerLine: lines[1] ?? '',
        lineCount: lines.length,
        bytes,
        chunks,
        firstChunkMs,
        totalMs: performance.now() - started,
      }
    },
    { path: CSV_PATH, token: owner.token },
  )) as StreamResult

  expect(result.status).toBe(200)
  expect(result.contentType).toContain('text/csv')
  expect(result.disposition).toContain('attachment; filename=')
  expect(result.firstLine).toContain('gross contribution')
  expect(result.firstLine).toContain(`The period is ${FROM}`)
  expect(result.firstLine).toContain(`up to but not including ${TO}`)
  expect(result.headerLine).toContain('Model,Category,Units,Days on hire')
  expect(result.lineCount).toBeGreaterThan(2)
  expect(result.bytes).toBeGreaterThan(0)
  expect(result.chunks).toBeGreaterThan(0)
  expect(result.firstChunkMs).toBeLessThanOrEqual(result.totalMs + 1)
  expect(result.totalMs).toBeLessThan(TIME_LIMIT_MS)

  note(
    `B12.4 staging report CSV passed for ${FROM} to but not including ${TO} at revision ` +
      `${healthBody.revision}. ${result.lineCount} lines, ${result.bytes} bytes, ${result.chunks} chunk(s), ` +
      `first chunk at ${result.firstChunkMs.toFixed(0)} ms, end at ${result.totalMs.toFixed(0)} ms. ` +
      'The staging file is small, so the chunk count is not a volume claim.',
  )
})
