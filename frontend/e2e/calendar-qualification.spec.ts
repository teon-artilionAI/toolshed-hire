import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { startBrowserClockWithTheApi } from './api-clock.ts'

const HOLIDAY = '2026-12-16'
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

test('a controlled clock sees the public holiday in the browser and the API', async ({ page, request }, testInfo) => {
  test.skip(process.env.TEST_BUSINESS_DATE !== HOLIDAY, 'Only for the aligned holiday qualification.')
  await startBrowserClockWithTheApi(page)
  const browserNow = await page.evaluate(() => new Date().toISOString())
  expect(browserNow.startsWith(HOLIDAY)).toBe(true)

  const dashboard = await counterDashboard(request)
  expect(dashboard.date).toBe(HOLIDAY)
  const trading = dashboard.trading as { opensAt: string | null; closesAt: string | null; closedKind: string | null }
  expect(trading.closedKind).toBe('public_holiday')
  expect(trading.opensAt).toBeNull()
  expect(trading.closesAt).toBeNull()

  const branchesResponse = await request.get('/api/branches')
  expect(branchesResponse.ok()).toBe(true)
  const branches = (await branchesResponse.json()) as {
    items: { name: string; closedDays: { day: string; reason: string; kind: string }[] }[]
  }
  const closed = branches.items.flatMap((branch) =>
    branch.closedDays.filter((day) => day.day === HOLIDAY).map((day) => ({ branch: branch.name, ...day })),
  )
  expect(closed.length).toBeGreaterThan(0)
  expect(closed.every((day) => day.kind === 'public_holiday')).toBe(true)

  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await page.getByLabel('Collect on').fill(HOLIDAY)
  await page.getByLabel('Bring back on').fill('2026-12-17')
  await expect(page.getByText(/closed for Day of Reconciliation/).first()).toBeVisible()
  const nextOpenDay = page.getByText(/The next open day is 17 Dec 2026/).first()
  await expect(nextOpenDay).toBeVisible()
  const nextOpenDayText = await nextOpenDay.innerText()

  const screenshot = testInfo.outputPath('holiday-browser.png')
  mkdirSync(dirname(screenshot), { recursive: true })
  await page.screenshot({ path: screenshot, fullPage: true })
  const evidence = {
    browserNow,
    apiDate: dashboard.date,
    apiTrading: trading,
    closedDays: closed,
    browserRefusal: 'closed for Day of Reconciliation',
    browserNextOpenDay: nextOpenDayText,
  }
  const evidencePath = testInfo.outputPath('holiday-qualification.json')
  writeFileSync(evidencePath, JSON.stringify(evidence, null, 2))
  await testInfo.attach('holiday-qualification', { path: evidencePath, contentType: 'application/json' })
  await testInfo.attach('holiday-browser', { path: screenshot, contentType: 'image/png' })
  console.log(JSON.stringify(evidence, null, 2))
})
