/**
 * The hire basket and a booking, against the real backend.
 *
 * There are two journeys here and they need different things from the backend.
 *
 * A visitor fills a basket from the catalogue, keeps it across a reload, and is
 * asked to sign in before reviewing it. That needs the catalogue routes and a
 * seeded database, and nobody signs in.
 *
 * A customer signs in, adds a model from the catalogue, reviews the cost,
 * holds the equipment, confirms the hire, finds it under My Hires, opens it
 * and cancels it. Then the other seeded customer signs in and is told that
 * the reference cannot be found. That is SC-03, SC-04, SC-07 and SC-08 end to
 * end, and it needs the reservation routes. `e2e/backend.ts` asks one of those
 * routes by name, because a healthy backend is not proof that it has them.
 * When they are not there, the journey skips itself and the run still passes.
 *
 * What a basket goes through before it is booked is in
 * reservation-changes.spec.ts. What the two files share is in booking.ts.
 *
 * The booking journey cancels what it booked, so the unit is free for the next
 * run. If it fails before that, a confirmed reservation is left on the seeded
 * customer for those dates, and the next run takes whichever model is free.
 *
 * The hold counts down with the browser's clock to an instant on the API's, so
 * when the API runs on a pinned clock the browser's is started at the same
 * time. api-clock.ts says how.
 */

import { expect, test } from '@playwright/test'
import { startBrowserClockWithTheApi } from './api-clock.ts'
import { blockingViolations } from './axe.ts'
import {
  BACKEND_NEEDED,
  RESERVATION_ROUTES_NEEDED,
  backendIsReachable,
  reservationRoutesArePresent,
} from './backend.ts'
import {
  BASKET_HEADING,
  BASKET_KEY,
  CLOCK_FACE,
  CONFIRMED_STEP,
  HOLD_STEP,
  RAND,
  REFERENCE,
  REVIEW_STEP,
  STORED_BASKET,
  addFreeModel,
  bookingRow,
  confirmationEmailSentence,
  figure,
  firstBranch,
  periodStarting,
  stepHeading,
} from './booking.ts'
import type { Period } from './booking.ts'
import { SECOND_CUSTOMER_EMAIL, signInAsCustomer } from './customer.ts'
import { SIGN_IN } from './routes.ts'

/** How far ahead each browser project books, so two runs side by side do not
 *  ask for the same unit on the same days. */
const COLLECT_IN_DAYS: Record<string, number> = {
  'chromium-desktop': 14,
  'chromium-mobile': 21,
}
const DEFAULT_COLLECT_IN_DAYS = 28

const CANCEL_REASON = 'Booked by a browser test'

/** Every key the page has put in web storage, the lasting store first. */
const STORED_KEYS = 'JSON.stringify([Object.keys(window.localStorage), Object.keys(window.sessionStorage)])'

function periodFor(projectName: string): Period {
  return periodStarting(COLLECT_IN_DAYS[projectName] ?? DEFAULT_COLLECT_IN_DAYS)
}

test.describe('the hire basket against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await backendIsReachable(request)), BACKEND_NEEDED)
  })

  test('a visitor fills a basket, keeps it across a reload, and is asked to sign in to book', async ({
    page,
    request,
  }, testInfo) => {
    const period = periodFor(testInfo.project.name)
    const branch = await firstBranch(request)

    const { name } = await addFreeModel(page, branch, period)

    // The basket is the one thing a visitor leaves in web storage. It names the
    // dates, the branch and the model, and nothing about a person.
    expect(await page.evaluate<string>(STORED_KEYS)).toBe(JSON.stringify([[], [BASKET_KEY]]))
    const stored = JSON.parse(await page.evaluate<string>(STORED_BASKET)) as Record<string, unknown>
    expect(stored).toMatchObject({ from: period.from, to: period.to, branchCode: branch.code })
    expect(stored.reservationId).toBeNull()

    // SC-04. The basket shows what was added, for the dates and the branch.
    await page.getByRole('link', { name: 'Go to my basket' }).click()
    await expect(page.getByRole('heading', { level: 1, name: BASKET_HEADING })).toBeVisible()
    await expect(page.getByRole('link', { name, exact: true })).toBeVisible()
    await expect(page.getByLabel('Collect on')).toHaveValue(period.from)
    await expect(page.getByLabel('Bring back on')).toHaveValue(period.to)
    await expect(page.getByLabel('Collect from')).toHaveValue(branch.code)
    // No price yet. The server prices the basket when it is reviewed.
    await expect(page.getByRole('main')).not.toContainText('Total with VAT')

    // A reload keeps it.
    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: BASKET_HEADING })).toBeVisible()
    await expect(page.getByRole('link', { name, exact: true })).toBeVisible()
    await expect(page.getByLabel('How many', { exact: true })).toHaveValue('1')

    await page.getByRole('button', { name: `One more ${name}` }).click()
    await expect(page.getByLabel('How many', { exact: true })).toHaveValue('2')
    expect(await blockingViolations(page)).toEqual([])

    // Reviewing needs an account, and the way back to the basket is kept.
    await page.getByRole('link', { name: 'Sign in to review and book' }).click()
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
    await expect(page).toHaveURL(/\/signin\?next=%2Fbasket$/)
  })
})

test.describe('a booking against the real backend', () => {
  test.beforeEach(async ({ page, request }) => {
    test.skip(!(await reservationRoutesArePresent(request)), RESERVATION_ROUTES_NEEDED)
    // The hold counts down to an instant on the API's clock.
    await startBrowserClockWithTheApi(page)
  })

  test('a customer adds a model, reviews, holds, confirms, finds the booking and cancels it', async ({
    page,
    request,
  }, testInfo) => {
    const period = periodFor(testInfo.project.name)
    const branch = await firstBranch(request)

    const { emailDeliverable } = await signInAsCustomer(page)
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

    const { name } = await addFreeModel(page, branch, period)
    await page.getByRole('link', { name: 'Go to my basket' }).click()
    await expect(page.getByRole('heading', { level: 1, name: BASKET_HEADING })).toBeVisible()
    await expect(page.getByRole('link', { name, exact: true })).toBeVisible()

    // Step 1. The server prices the basket, and the screen shows its figures.
    await page.getByRole('button', { name: 'Review and book' }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    await expect(page.getByRole('table')).toContainText(name)
    await expect(figure(page, 'Hire before VAT')).toHaveText(RAND)
    await expect(figure(page, /^VAT$/)).toHaveText(RAND)
    await expect(figure(page, 'Total with VAT')).toHaveText(RAND)
    await expect(figure(page, 'Deposit')).toHaveText(RAND)
    await expect(page.getByText(/The deposit is held when you collect the equipment/)).toBeVisible()
    const total = await figure(page, 'Total with VAT').innerText()

    // Step 2. The equipment is held and the clock is running.
    await page.getByRole('button', { name: 'Hold this equipment' }).click()
    await expect(stepHeading(page, HOLD_STEP)).toBeFocused()
    const timer = page.getByRole('timer', { name: 'Time left to confirm' })
    await expect(timer).toHaveText(CLOCK_FACE)
    await expect(timer).toHaveAttribute('aria-live', 'off')
    await expect(page.getByText(/^Held until \d{2}:\d{2}\.$/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    // Step 3. The hire is confirmed and has a reference.
    await page.getByRole('button', { name: 'Confirm this hire' }).click()
    await expect(stepHeading(page, CONFIRMED_STEP)).toBeFocused()
    const confirmation = page.getByText(new RegExp(`^Booking ${REFERENCE.source} is confirmed$`))
    await expect(confirmation).toBeVisible()
    const reference = REFERENCE.exec(await confirmation.innerText())?.[0] ?? ''
    expect(reference).toMatch(REFERENCE)
    // The email is promised only when it can reach the customer's address.
    // Otherwise the screen says plainly that it will not arrive.
    await expect(page.getByText(confirmationEmailSentence(emailDeliverable))).toBeVisible()
    await expect(figure(page, 'Total with VAT')).toHaveText(total)
    // The basket was booked, so it is empty again.
    expect(await page.evaluate<string | null>(STORED_BASKET)).toBeNull()

    // SC-07. The booking is in the customer's list, confirmed, with its total.
    await page.getByRole('link', { name: 'See my hires' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'My hires' })).toBeVisible()
    const row = bookingRow(page, reference)
    await expect(row).toContainText('Confirmed')
    await expect(row).toContainText(branch.name)
    await expect(row).toContainText(total)
    expect(await blockingViolations(page)).toEqual([])

    // SC-08. The booking in full, then its cancellation.
    await row.getByRole('link', { name: `View booking ${reference}` }).click()
    await expect(page.getByRole('heading', { level: 1, name: reference })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/reservations/${reference}$`))
    await expect(page.getByRole('table')).toContainText(name)
    await expect(figure(page, 'Total with VAT')).toHaveText(total)
    await expect(page.getByText(/Charges appear here once the equipment has been collected/)).toBeVisible()

    await page.getByRole('button', { name: 'Cancel this booking' }).click()
    await expect(page.getByRole('heading', { name: `Cancel ${reference}?` })).toBeFocused()
    await page.getByLabel(/Why are you cancelling/).fill(CANCEL_REASON)
    await page.getByRole('button', { name: 'Yes, cancel this booking' }).click()

    await expect(page.getByText('This booking has been cancelled')).toBeVisible()
    await expect(page.getByText(`The reason given was "${CANCEL_REASON}".`)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancel this booking' })).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    // Another customer who opens that reference is told it cannot be found,
    // and is shown nothing of the booking.
    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible()
    await signInAsCustomer(page, SECOND_CUSTOMER_EMAIL)
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
    await page.goto(`/reservations/${reference}`)
    await expect(page.getByRole('heading', { level: 1, name: 'We cannot find that booking' })).toBeVisible()
    await expect(page.getByText('No booking with that reference')).toBeVisible()
    await expect(page.getByRole('main')).not.toContainText(name)
    await expect(page.getByRole('main')).not.toContainText(total)
    expect(await blockingViolations(page)).toEqual([])
  })
})
