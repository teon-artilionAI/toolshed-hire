/**
 * The counter's day and the locator, against the real backend.
 *
 * A seeded counter assistant signs in and lands on the dashboard, which names
 * their branch and shows the five figures. They open the diary for today, then
 * the whole of next week, and then find a seeded unit by its tag in the
 * locator. That is SC-10, SC-11 and SC-17 read end to end, under the same
 * Content Security Policy a visitor gets.
 *
 * The figures are checked to be whole numbers and not particular ones, because
 * the other journeys book and check out units at the same branches while this
 * one runs. The diary is checked to have loaded the days it was asked for, with
 * or without anything on them. The unit is TSH-DR-0042, which the seed always
 * makes at Cape Town CBD, and the locator searches every branch, so both
 * assistants find it.
 *
 * It needs the dashboard, the diary and the locator, which a healthy backend
 * may not have yet, so `e2e/backend.ts` asks for each of them by name. When
 * they are not there the journey skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { OVERVIEW_ROUTES_NEEDED, overviewRoutesArePresent } from './backend.ts'
import { dateFromToday, dayInWords, mondayOf } from './hire-dates.ts'
import { BLV_COUNTER_EMAIL, CBD_COUNTER_EMAIL, signInAsStaff, staffFor } from './staff.ts'

/** The branch each seeded assistant works at, by the name the API gives it. */
const BRANCH_OF: Record<string, string> = {
  [CBD_COUNTER_EMAIL]: 'Cape Town CBD',
  [BLV_COUNTER_EMAIL]: 'Bellville',
}

const FIGURES = ['Collections due today', 'Returns due today', 'Overdue now', 'Out on hire', 'Quarantined']

/** A unit the seed always makes, and where. */
const SEEDED_TAG = 'TSH-DR-0042'
const SEEDED_TAG_BRANCH = 'Cape Town CBD'

const DAYS_IN_WEEK = 7

/** The value of one figure across the top of the dashboard. */
function figureValue(page: Page, label: string) {
  return page.getByText(label, { exact: true }).locator('xpath=..').locator('p').nth(1)
}

test.describe('the counter overview against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await overviewRoutesArePresent(request)), OVERVIEW_ROUTES_NEEDED)
  })

  test('an assistant sees today at their branch, the diary for today and next week, and finds a unit', async ({
    page,
  }, testInfo) => {
    const email = staffFor(testInfo.project.name)
    const branch = BRANCH_OF[email]
    await signInAsStaff(page, email)

    // SC-10. The branch, today, and the five figures as whole numbers.
    await expect(page.getByRole('status').filter({ hasText: new RegExp(`^${branch}, .+\\. Read at \\d{2}:\\d{2}\\.$`) })).toBeVisible()
    for (const label of FIGURES) await expect(figureValue(page, label)).toHaveText(/^\d+$/)
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    // SC-11. Today, a day on its own.
    const today = dateFromToday(0)
    await page.goto('/counter/diary')
    await expect(page.getByRole('heading', { level: 1, name: 'Branch diary' })).toBeVisible()
    await expect(page.getByText(`${dayInWords(today)} at ${branch}.`)).toBeVisible()
    await expect(
      page
        .getByRole('heading', { level: 2, name: new RegExp(`^${dayInWords(today)}`) })
        .or(page.getByText('Nothing goes out or comes back on this day')),
    ).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    // The whole of next week, from its Monday, with the day in the address.
    await page.getByRole('button', { name: 'Whole week' }).click()
    await page.getByRole('button', { name: 'Next week' }).click()
    const sameDayNextWeek = dateFromToday(DAYS_IN_WEEK)
    await expect(page).toHaveURL(new RegExp(`/counter/diary\\?date=${sameDayNextWeek}&view=week$`))
    await expect(page.getByText(`The week starting ${dayInWords(mondayOf(sameDayNextWeek))} at ${branch}.`)).toBeVisible()
    const weekLoaded = page.getByRole('heading', { level: 2, name: new RegExp(`^${dayInWords(mondayOf(sameDayNextWeek))}`) })
    await expect(weekLoaded.or(page.getByText('Nothing goes out or comes back this week'))).toBeVisible()
    if (await weekLoaded.isVisible()) await expect(page.getByRole('heading', { level: 2 })).toHaveCount(DAYS_IN_WEEK)
    expect(await blockingViolations(page)).toEqual([])

    // A reload keeps the week.
    await page.reload()
    await expect(page.getByText(`The week starting ${dayInWords(mondayOf(sameDayNextWeek))} at ${branch}.`)).toBeVisible()

    // SC-17. A seeded unit, found by its tag, at the branch it belongs to.
    await page.goto('/counter/locator')
    await expect(page.getByRole('heading', { level: 1, name: 'Where is it' })).toBeVisible()
    await page.getByLabel('Asset tag or model').fill(SEEDED_TAG)
    const unit = page.getByRole('row').filter({ hasText: SEEDED_TAG })
    await expect(unit).toBeVisible()
    await expect(unit.getByText(SEEDED_TAG_BRANCH)).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/counter/locator\\?q=${SEEDED_TAG}$`))
    expect(await blockingViolations(page)).toEqual([])
  })
})
