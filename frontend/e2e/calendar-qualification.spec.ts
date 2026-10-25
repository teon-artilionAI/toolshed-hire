import { expect, test } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { startBrowserClockWithTheApi } from './api-clock.ts'

const SCRATCH = 'C:/Users/teon/AppData/Local/hermes/cache/scratch/toolshed-calendar-qualification'
const HOLIDAY = '2026-12-16'

test('a controlled clock sees the public holiday in the browser and the API', async ({ page, request }) => {
  test.skip(process.env.TEST_BUSINESS_DATE !== HOLIDAY, 'Only for the aligned holiday qualification.')
  mkdirSync(SCRATCH, { recursive: true })
  await startBrowserClockWithTheApi(page)
  const browserNow = await page.evaluate(() => new Date().toISOString())
  expect(browserNow.startsWith(HOLIDAY)).toBe(true)

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

  await page.screenshot({ path: join(SCRATCH, 'holiday-browser.png'), fullPage: true })
  writeFileSync(
    join(SCRATCH, 'holiday-qualification.json'),
    JSON.stringify({ browserNow, closedDays: closed, browserRefusal: 'closed for Day of Reconciliation' }, null, 2),
  )
  console.log(JSON.stringify({ browserNow, closedDays: closed, browserRefusal: 'closed for Day of Reconciliation' }, null, 2))
})
