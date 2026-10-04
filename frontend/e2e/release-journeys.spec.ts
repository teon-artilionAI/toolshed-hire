/**
 * The three role journeys of the release, end to end, locally and on staging.
 *
 * A customer books one unit, holds it, confirms it, finds it under My Hires
 * and cancels it. That is SC-03, SC-04, SC-07 and SC-08. A counter assistant
 * books a unit for the seeded trade customer for today, checks it out and
 * takes it straight back with the deposit released in full, which is SC-12,
 * SC-13, SC-14 and SC-15, with the way it finishes when the branch has closed
 * for the day in release-counter.ts. The owner opens the dashboard, the report
 * for the last full month, the asset register and the audit trail, which is
 * SC-19, SC-22, SC-21 and SC-24, and changes nothing.
 *
 * Each journey is tagged `@staging`, so it runs on the staging project after
 * each staging deploy as well as on the local projects. On staging they must
 * leave the site as they found it apart from the new booking history. So the
 * customer cancels what they booked far enough ahead that it is never a late
 * cancellation, the counter brings back what it checked out or has its
 * booking cancelled, nobody new is registered, and the owner only reads.
 * Staging runs on the real clock, so nothing here depends on the API's clock
 * being pinned, and nothing pins the browser's either.
 *
 * On a local project a journey skips itself when the backend or its routes are
 * not there, the way the other backend specs do, and the run still passes. On
 * staging it never skips, because a skipped journey there would hide a broken
 * deploy. The emails a booking sends are not checked here, because staging
 * may still run an earlier build of the screens. reservation.spec.ts checks
 * the confirmation's words against the session.
 */

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { assetRegisterRoutesArePresent } from './admin-assets-backend.ts'
import { RESERVATION_ROUTES_NEEDED, RETURN_ROUTES_NEEDED, reservationRoutesArePresent, returnRoutesArePresent } from './backend.ts'
import {
  BASKET_HEADING,
  CONFIRMED_STEP,
  HOLD_STEP,
  RAND,
  REFERENCE,
  REVIEW_STEP,
  addFreeModel,
  bookingRow,
  figure,
  firstBranch,
  periodStarting,
  stepHeading,
} from './booking.ts'
import { signInAsCustomer } from './customer.ts'
import { dateFromToday } from './hire-dates.ts'
import { operationsRoutesArePresent } from './operations-backend.ts'
import { bookForTheTradeCustomer } from './release-counter.ts'
import { reportingRoutesArePresent } from './reporting-backend.ts'
import { signInAsOwner, signInAsStaff, staffFor } from './staff.ts'
import { STAGING_PROJECT, STAGING_TAG } from './staging-run.ts'
import { note, onStaging } from './staging.ts'

/** How far ahead the customer books in each project. Far enough that no other
 *  journey of a run books the same days, and far enough that cancelling it is
 *  never late. */
const COLLECT_IN_DAYS: Record<string, number> = {
  'chromium-desktop': 42,
  'chromium-mobile': 49,
  [STAGING_PROJECT]: 35,
}
const DEFAULT_COLLECT_IN_DAYS = 56

const CANCEL_REASON = 'Booked by the release journey'

/** The seeded branches, by the names the API gives them. */
const BRANCH_NAMES = ['Cape Town CBD', 'Bellville', 'Somerset West']

const OWNER_ROUTES_NEEDED =
  'This needs the reporting, asset register and audit routes on the real backend, and one of them answered ' +
  'as a route that is not there. Run the browser tests again against a backend that has all three.'

/** Skip on a local project when the routes are not there. Never on staging. */
async function skipLocallyUnless(present: (request: APIRequestContext) => Promise<boolean>, request: APIRequestContext, reason: string) {
  if (onStaging()) return
  test.skip(!(await present(request)), reason)
}

/** The last full calendar month at the branches, the way the API counts it. */
function lastFullMonth(): { from: string; to: string } {
  const to = `${dateFromToday(0).slice(0, 7)}-01`
  const dayBefore = new Date(`${to}T00:00:00Z`)
  dayBefore.setUTCDate(dayBefore.getUTCDate() - 1)
  return { from: `${dayBefore.toISOString().slice(0, 7)}-01`, to }
}

test('a customer books, holds, confirms and cancels a unit', { tag: STAGING_TAG }, async ({ page, request }, testInfo) => {
  await skipLocallyUnless(reservationRoutesArePresent, request, RESERVATION_ROUTES_NEEDED)
  const period = periodStarting(COLLECT_IN_DAYS[testInfo.project.name] ?? DEFAULT_COLLECT_IN_DAYS)
  const branch = await firstBranch(request)

  await signInAsCustomer(page)
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  const { name } = await addFreeModel(page, branch, period)
  await page.getByRole('link', { name: 'Go to my basket' }).click()
  await expect(page.getByRole('heading', { level: 1, name: BASKET_HEADING })).toBeVisible()

  // SC-04. Priced by the server, held, and confirmed with a reference.
  await page.getByRole('button', { name: 'Review and book' }).click()
  await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
  await expect(figure(page, 'Total with VAT')).toHaveText(RAND)
  const total = await figure(page, 'Total with VAT').innerText()
  await page.getByRole('button', { name: 'Hold this equipment' }).click()
  await expect(stepHeading(page, HOLD_STEP)).toBeFocused()
  await expect(page.getByRole('timer', { name: 'Time left to confirm' })).toBeVisible()
  await page.getByRole('button', { name: 'Confirm this hire' }).click()
  await expect(stepHeading(page, CONFIRMED_STEP)).toBeFocused()
  const confirmation = page.getByText(new RegExp(`^Booking ${REFERENCE.source} is confirmed$`))
  const reference = REFERENCE.exec(await confirmation.innerText())?.[0] ?? ''
  expect(reference).toMatch(REFERENCE)

  // SC-07, then SC-08 and the cancellation.
  await page.getByRole('link', { name: 'See my hires' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'My hires' })).toBeVisible()
  const row = bookingRow(page, reference)
  await expect(row).toContainText('Confirmed')
  await expect(row).toContainText(total)
  await row.getByRole('link', { name: `View booking ${reference}` }).click()
  await expect(page.getByRole('heading', { level: 1, name: reference })).toBeVisible()
  await expect(page.getByRole('table')).toContainText(name)
  await page.getByRole('button', { name: 'Cancel this booking' }).click()
  await expect(page.getByRole('heading', { name: `Cancel ${reference}?` })).toBeFocused()
  await page.getByLabel(/Why are you cancelling/).fill(CANCEL_REASON)
  await page.getByRole('button', { name: 'Yes, cancel this booking' }).click()
  await expect(page.getByText('This booking has been cancelled')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cancel this booking' })).toHaveCount(0)
  note(`The customer booked ${reference} at ${branch.name} from ${period.from} to ${period.to}, and cancelled it.`)
})

test('a counter assistant books a unit for the trade customer, checks it out and takes it back', { tag: STAGING_TAG }, async ({
  page,
  browser,
  request,
}, testInfo) => {
  await skipLocallyUnless(returnRoutesArePresent, request, RETURN_ROUTES_NEEDED)

  await signInAsStaff(page, staffFor(testInfo.project.name))
  const outcome = await bookForTheTradeCustomer(page, browser, testInfo.project.use.baseURL)

  expect(['out and back today', 'booked ahead and cancelled']).toContain(outcome)
})

test('the owner opens the dashboard, last month\'s report, the asset register and the audit trail', { tag: STAGING_TAG }, async ({
  page,
  request,
}) => {
  await skipLocallyUnless(
    async (context) =>
      (await reportingRoutesArePresent(context)) &&
      (await assetRegisterRoutesArePresent(context)) &&
      (await operationsRoutesArePresent(context)),
    request,
    OWNER_ROUTES_NEEDED,
  )
  await signInAsOwner(page)

  // SC-19. The three branches, read from the server.
  await expect(page.getByRole('heading', { level: 2, name: 'Branch by branch' })).toBeVisible()
  for (const branchName of BRANCH_NAMES) await expect(page.getByRole('article', { name: branchName })).toBeVisible()

  // SC-22. The last full month by model, with the period in the address.
  const { from, to } = lastFullMonth()
  await page.goto('/admin/reports')
  await expect(page.getByRole('heading', { level: 1, name: 'Utilisation and gross contribution' })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`/admin/reports\\?from=${from}&to=${to}&groupBy=model$`))
  await expect(page.getByRole('heading', { level: 2, name: 'Broken down by model' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Totals for the whole report' }).getByText('Gross contribution', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'What these figures mean' })).toContainText('never profit')

  // SC-21. The register, one page of units in tag order.
  await page.goto('/admin/assets')
  await expect(page.getByRole('heading', { level: 1, name: 'Asset register' })).toBeVisible()
  const units = page.getByRole('region', { name: 'The units' })
  await expect(units.getByRole('status').first()).toHaveText(/^[1-9]\d* units? match(es)?, in tag order\.$/)
  await expect(units.getByRole('rowheader').first()).toBeVisible()

  // SC-24. The trail, newest first, which nobody can change.
  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { level: 1, name: 'Audit and notification log' })).toBeVisible()
  await expect(page.getByText('Nobody can change this record')).toBeVisible()
  const events = page.getByRole('region', { name: 'The events' })
  await expect(events.getByRole('status').first()).toHaveText(/^\d+ events? match(es)?, newest first\.$/)
  await expect(events.getByRole('article').first()).toBeVisible()
  note(`The owner read the dashboard, the report from ${from} to ${to}, the asset register and the audit trail, and changed nothing.`)
})
