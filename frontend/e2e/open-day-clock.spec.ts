import { expect, test } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { startBrowserClockWithTheApi } from './api-clock.ts'

const SCRATCH = 'C:/Users/teon/AppData/Local/hermes/cache/scratch/toolshed-calendar-qualification'
const OPEN_DAY = '2026-12-15'

test('the open aligned day is effective in the browser', async ({ page }) => {
  test.skip(process.env.TEST_BUSINESS_DATE !== OPEN_DAY, 'Only for the aligned open-day qualification.')
  mkdirSync(SCRATCH, { recursive: true })
  await startBrowserClockWithTheApi(page)
  const browserNow = await page.evaluate(() => new Date().toISOString())
  expect(browserNow.startsWith(OPEN_DAY)).toBe(true)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await expect(page.getByLabel('Collect on')).toHaveValue(OPEN_DAY)
  await page.screenshot({ path: join(SCRATCH, 'open-day-browser.png'), fullPage: true })
  writeFileSync(join(SCRATCH, 'open-day-clock.json'), JSON.stringify({ browserNow, collectOn: OPEN_DAY }, null, 2))
  console.log(JSON.stringify({ browserNow, collectOn: OPEN_DAY }, null, 2))
})
