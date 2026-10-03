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
 * A second journey books one unit for today for a new walk in, finds it due
 * out on the dashboard and in the diary, and marks it as a no show from the
 * diary. That is the one thing these screens change, sent to the real API and
 * read back from it. Staff may mark a booking from the start of its first day,
 * and once the branch has closed on that day the server's sweep marks it by
 * itself. So a run after closing time finds the booking already a no show, with
 * nothing to press, and checks that instead.
 *
 * It needs the dashboard, the diary and the locator, which a healthy backend
 * may not have yet, so `e2e/backend.ts` asks for each of them by name. When
 * they are not there the journey skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { OVERVIEW_ROUTES_NEEDED, overviewRoutesArePresent } from './backend.ts'
import { bookForTodayAtTheCounter } from './counter-booking.ts'
import type { CounterBooking } from './counter-booking.ts'
import { clockTimeAtTheBranches, dateFromToday, dayInWords, mondayOf } from './hire-dates.ts'
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

/** What the assistant gives as the reason nobody came. */
const NO_SHOW_REASON = 'Did not arrive and did not answer the phone.'

/** How the diary and the answer to the no show name the status. */
const NOT_COLLECTED_YET = 'Booked, not collected yet'
const NO_SHOW = 'No show'

/** The value of one figure across the top of the dashboard. */
function figureValue(page: Page, label: string) {
  return page.getByText(label, { exact: true }).locator('xpath=..').locator('p').nth(1)
}

/** The line above the figures, once the dashboard of a branch has loaded. */
function dashboardReadLine(page: Page, branch: string): Locator {
  return page.getByRole('status').filter({ hasText: new RegExp(`^${branch}, .+\\. Read at \\d{2}:\\d{2}\\.$`) })
}

/** One booking in the dashboard's list of collections due today. */
function dueOutToday(page: Page, reference: string): Locator {
  return page.getByRole('list', { name: 'Collections due today' }).getByRole('listitem').filter({ hasText: reference })
}

/** One booking in the diary's list of what goes out today. */
function goingOutToday(page: Page, reference: string): Locator {
  return page
    .getByRole('list', { name: `Going out on ${dayInWords(dateFromToday(0))}` })
    .getByRole('listitem')
    .filter({ hasText: reference })
}

/**
 * Whether the branch has closed for today, by the clock in Cape Town and the
 * hours the API gives the branch. From the minute it closes the sweep may
 * already have marked today's bookings as no shows.
 */
async function hasClosedForToday(request: APIRequestContext, branch: string): Promise<boolean> {
  const answer = await request.get('/api/branches')
  expect(answer.ok(), `the branch route answered ${answer.status()}`).toBe(true)
  const { items } = (await answer.json()) as { items: { name: string; closesAt: string }[] }
  const closesAt = items.find((item) => item.name === branch)?.closesAt
  expect(closesAt, `the API lists no branch called ${branch}`).toBeDefined()
  return clockTimeAtTheBranches() >= (closesAt ?? '')
}

/** Before closing. The booking is due out, and the assistant marks it. */
async function markAsNoShow(page: Page, { customerName, reference }: CounterBooking, branch: string) {
  // SC-10. Due out today, with the way to check it out.
  await page.goto('/counter')
  await expect(dashboardReadLine(page, branch)).toBeVisible()
  await expect(dueOutToday(page, reference).getByRole('link', { name: `Check out ${reference}` })).toBeVisible()

  // SC-11. Not collected yet, and the server offers the no show.
  await page.goto('/counter/diary')
  const booking = goingOutToday(page, reference)
  await expect(booking.getByText(NOT_COLLECTED_YET, { exact: true })).toBeVisible()
  await booking.getByRole('button', { name: `Mark as no show ${reference}` }).click()
  const reason = booking.getByLabel('Why did the booking not go out?')
  await expect(reason).toBeFocused()
  await reason.fill(NO_SHOW_REASON)
  expect(await blockingViolations(page)).toEqual([])
  await booking.getByRole('button', { name: 'Yes, mark as no show' }).click()

  // The server's answer replaces the question, and the diary is read again.
  const answered = booking.getByRole('status')
  await expect(answered).toBeFocused()
  await expect(answered).toContainText(`${reference} is now`)
  await expect(answered.getByText(NO_SHOW, { exact: true })).toBeVisible()
  await expect(answered).toContainText(`the strike is recorded against ${customerName}`)
  await expect(booking.getByText(NOT_COLLECTED_YET, { exact: true })).toHaveCount(0)
  await expect(booking.getByRole('link', { name: `Check out ${reference}` })).toHaveCount(0)

  // A reload shows only what the server now has.
  await page.reload()
  await expect(booking.getByText(NO_SHOW, { exact: true })).toBeVisible()
  await expect(booking.getByRole('button', { name: /^Mark as no show/ })).toHaveCount(0)

  // SC-10. No longer due out.
  await page.goto('/counter')
  await expect(dashboardReadLine(page, branch)).toBeVisible()
  await expect(dueOutToday(page, reference)).toHaveCount(0)
}

/** After closing. The sweep has marked the booking, and nothing is offered. */
async function findSweptAlready(page: Page, { reference }: CounterBooking, branch: string) {
  await page.goto('/counter')
  await expect(dashboardReadLine(page, branch)).toBeVisible()
  await expect(dueOutToday(page, reference)).toHaveCount(0)

  await page.goto('/counter/diary')
  const booking = goingOutToday(page, reference)
  await expect(booking.getByText(NO_SHOW, { exact: true })).toBeVisible()
  await expect(booking.getByRole('button', { name: /^Mark as no show/ })).toHaveCount(0)
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
    await expect(dashboardReadLine(page, branch)).toBeVisible()
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

  test('an assistant books for today, sees it due out, and marks it as a no show from the diary', async ({
    page,
    request,
  }, testInfo) => {
    const email = staffFor(testInfo.project.name)
    const branch = BRANCH_OF[email]
    await signInAsStaff(page, email)
    const booking = await bookForTodayAtTheCounter(page, testInfo.project.name)

    if (await hasClosedForToday(request, branch)) await findSweptAlready(page, booking, branch)
    else await markAsNoShow(page, booking, branch)
  })
})
