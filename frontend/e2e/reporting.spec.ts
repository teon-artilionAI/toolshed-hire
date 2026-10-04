/**
 * The owner's dashboard and the utilisation report, against the real backend.
 *
 * The seeded owner signs in and lands on the dashboard, which shows the three
 * branches. They open the report, which starts at the last full month by
 * model, and see rows and the gross contribution figure. They break it down by
 * branch instead, then download the CSV and the spec reads the file the
 * browser saved. That is SC-19 and SC-22 end to end, under the same Content
 * Security Policy a visitor gets.
 *
 * The figures are checked for their shape and not for particular values,
 * because the other journeys book and return units while this one runs. The
 * CSV is checked for its name, its first line, which says the figures are
 * gross contribution and not profit, and its header row.
 *
 * It needs the reporting routes, which a healthy backend may not have yet, so
 * `e2e/reporting-backend.ts` asks for each of them by name. When they are not
 * there the spec skips itself and the run still passes.
 */

import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { dateFromToday } from './hire-dates.ts'
import { REPORTING_ROUTES_NEEDED, reportingRoutesArePresent } from './reporting-backend.ts'
import { signInAsOwner } from './staff.ts'

/** The seeded branches, by the names the API gives them. */
const BRANCH_NAMES = ['Cape Town CBD', 'Bellville', 'Somerset West']

const REPORT_HEADING = 'Utilisation and gross contribution'

/** A UTF-8 byte order mark, which a CSV may start with so a spreadsheet reads it right. */
const BYTE_ORDER_MARK = /^﻿/

/** The last full calendar month at the branches, the way the API counts it. */
function lastFullMonth(): { from: string; to: string } {
  const today = dateFromToday(0)
  const to = `${today.slice(0, 7)}-01`
  const dayBefore = new Date(`${to}T00:00:00Z`)
  dayBefore.setUTCDate(dayBefore.getUTCDate() - 1)
  return { from: `${dayBefore.toISOString().slice(0, 7)}-01`, to }
}

test.describe('the owner reporting against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await reportingRoutesArePresent(request)), REPORTING_ROUTES_NEEDED)
  })

  test('the owner sees the three branches, last month by model and by branch, and downloads the CSV', async ({
    page,
  }) => {
    await signInAsOwner(page)

    // SC-19. Three branches, read from the server.
    await expect(page.getByRole('heading', { level: 2, name: 'Branch by branch' })).toBeVisible()
    await expect(page.getByRole('article')).toHaveCount(BRANCH_NAMES.length)
    for (const name of BRANCH_NAMES) await expect(page.getByRole('article', { name })).toBeVisible()
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    // SC-22. The last full month by model, with the period in the address.
    const { from, to } = lastFullMonth()
    await page.goto('/admin/reports')
    await expect(page.getByRole('heading', { level: 1, name: REPORT_HEADING })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/admin/reports\\?from=${from}&to=${to}&groupBy=model$`))
    await expect(page.getByRole('heading', { level: 2, name: 'Broken down by model' })).toBeVisible()
    await expect(page.getByRole('rowheader').first()).toBeVisible()
    const totals = page.getByRole('region', { name: 'Totals for the whole report' })
    await expect(totals.getByText('Gross contribution', { exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'What these figures mean' })).toContainText('never profit')
    expect(await blockingViolations(page)).toEqual([])

    // By branch, one row for each branch.
    await page.getByLabel('Break the figures down by').selectOption('branch')
    await expect(page).toHaveURL(new RegExp(`groupBy=branch$`))
    await expect(page.getByRole('heading', { level: 2, name: 'Broken down by branch' })).toBeVisible()
    await expect(page.getByRole('rowheader')).toHaveCount(BRANCH_NAMES.length)

    // The CSV, fetched with the token and saved under the server's name.
    const fileName = `toolshed-gross-contribution-branch-${from}-${to}.csv`
    const saving = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download CSV' }).click()
    const download = await saving
    expect(download.suggestedFilename()).toBe(fileName)
    await expect(page.getByText(`Downloaded ${fileName}.`)).toBeVisible()

    const lines = (await readFile(await download.path(), 'utf8')).replace(BYTE_ORDER_MARK, '').split(/\r?\n/)
    expect(lines[0]).toMatch(/gross contribution/i)
    expect(lines[0]).toMatch(/not profit/i)
    const header = lines.find(
      (line, index) => index > 0 && /utilisation/i.test(line) && /gross ?contribution/i.test(line) && !/profit/i.test(line),
    )
    expect(header, 'the CSV has a header row naming utilisation and gross contribution').toBeDefined()
  })
})
