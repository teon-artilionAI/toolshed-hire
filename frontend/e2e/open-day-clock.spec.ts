import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { startBrowserClockWithTheApi } from './api-clock.ts'

const OPEN_DAY = '2026-12-15'
const STAFF_EMAIL = process.env.E2E_STAFF_EMAIL ?? 'elmarie@toolshedhire.co.za'
const STAFF_PASSWORD = process.env.E2E_STAFF_PASSWORD ?? 'toolshed-dev-password'

async function counterDashboard(request: APIRequestContext): Promise<Record<string, unknown>> {
  const login = await request.post('/api/auth/login', {
    data: { email: STAFF_EMAIL, password: STAFF_PASSWORD },
  })
  expect(login.ok()).toBe(true)
  const token = (await login.json()) as { accessToken: string }
  const dashboard = await request.get('/api/counter/dashboard?branchCode=CBD', {
    headers: { Authorization: `Bearer ${token.accessToken}` },
  })
  expect(dashboard.ok()).toBe(true)
  return (await dashboard.json()) as Record<string, unknown>
}

test('the open aligned day is effective in the browser and the API', async ({ page, request }, testInfo) => {
  test.skip(process.env.TEST_BUSINESS_DATE !== OPEN_DAY, 'Only for the aligned open-day qualification.')
  await startBrowserClockWithTheApi(page)
  const browserNow = await page.evaluate(() => new Date().toISOString())
  expect(browserNow.startsWith(OPEN_DAY)).toBe(true)

  const dashboard = await counterDashboard(request)
  expect(dashboard.date).toBe(OPEN_DAY)
  const trading = dashboard.trading as { opensAt: string | null; closesAt: string | null; closedKind: string | null }
  expect(trading.closedKind).toBeNull()
  expect(trading.opensAt).not.toBeNull()
  expect(trading.closesAt).not.toBeNull()

  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByLabel('Collect on')).toHaveValue(OPEN_DAY)
  const screenshot = testInfo.outputPath('open-day-browser.png')
  mkdirSync(dirname(screenshot), { recursive: true })
  await page.screenshot({ path: screenshot, fullPage: true })
  const evidence = { browserNow, apiDate: dashboard.date, apiTrading: trading, collectOn: OPEN_DAY }
  const evidencePath = testInfo.outputPath('open-day-clock.json')
  writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
  await testInfo.attach('open-day-clock', { path: evidencePath, contentType: 'application/json' })
  await testInfo.attach('open-day-browser', { path: screenshot, contentType: 'image/png' })
  console.log(JSON.stringify(evidence, null, 2))
})
