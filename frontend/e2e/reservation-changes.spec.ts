/**
 * A basket that changes on its way to a booking, against the real backend.
 *
 * The other seeded customer signs in and puts two models in one basket. The
 * journey then goes through what reservation.spec.ts leaves out.
 *
 * - Two models in one basket are one reservation with two lines.
 * - Going back from the review and reviewing again makes no second draft.
 * - Asking for more of a model than the branch has is refused when the hold is
 *   asked for, in the server's own sentence, and the basket can be changed and
 *   tried again. The draft that was replaced is cancelled.
 * - A reload in the middle of a hold picks the same reservation up.
 * - A draft that was replaced before it held anything is an abandoned basket
 *   and not a cancelled booking, so the server leaves it out of My Hires. The
 *   one that was held and then released is a cancelled booking and stays.
 * - A review the customer walks away from stays behind as a booking that was
 *   not finished. My Hires leaves it out until the filter asks for it.
 *
 * The journey finds its own reservations by the references the API answered
 * with, so it does not matter what earlier runs left in the database. It
 * releases the hold it took and cancels the draft it left, so every unit is
 * free again for the next run.
 *
 * The hold counts down with the browser's clock to an instant on the API's, so
 * when the API runs on a pinned clock the browser's is started at the same
 * time. api-clock.ts says how.
 */

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { startBrowserClockWithTheApi } from './api-clock.ts'
import { blockingViolations } from './axe.ts'
import { RESERVATION_ROUTES_NEEDED, reservationRoutesArePresent } from './backend.ts'
import {
  BASKET_HEADING,
  BASKET_STEP,
  CLOCK_FACE,
  HOLD_STEP,
  REVIEW_STEP,
  STORED_BASKET,
  addFreeModel,
  bookingRow,
  firstBranch,
  periodStarting,
  stepHeading,
  watchReservationsMade,
} from './booking.ts'
import type { BranchOnTheWire, ModelInBasket, Period } from './booking.ts'
import { SECOND_CUSTOMER_EMAIL, signInAsCustomer } from './customer.ts'

/** How far ahead each browser project books. These are other dates than the
 *  ones reservation.spec.ts books, so no journey competes with another. */
const COLLECT_IN_DAYS: Record<string, number> = {
  'chromium-desktop': 35,
  'chromium-mobile': 42,
}
const DEFAULT_COLLECT_IN_DAYS = 49

/** The most of one model a booking may ask for. The basket goes no higher. */
const MOST_OF_ONE_MODEL = 10

const REVIEW = 'Review and book'
const CHANGE_BASKET = 'Change my basket'
const HOLD = 'Hold this equipment'
const HOLD_REFUSED = 'We could not hold everything in your basket'
const HOLD_ROUTE = /^\/api\/reservations\/[^/]+\/hold$/
const HTTP_CONFLICT = 409

/** Whether a branch can supply a number of one model for the whole period. */
async function branchCanSupply(
  request: APIRequestContext,
  model: ModelInBasket,
  branch: BranchOnTheWire,
  period: Period,
  quantity: number,
): Promise<boolean> {
  const answer = await request.get(
    `/api/catalogue/models/${encodeURIComponent(model.slug)}/availability` +
      `?from=${period.from}&to=${period.to}&quantity=${quantity}`,
  )
  expect(answer.ok(), `the availability route answered ${answer.status()}`).toBe(true)
  const { branches } = (await answer.json()) as { branches: { branchCode: string; available: boolean }[] }
  return branches.some((entry) => entry.branchCode === branch.code && entry.available)
}

test.describe('a basket that changes, against the real backend', () => {
  test.beforeEach(async ({ page, request }) => {
    test.skip(!(await reservationRoutesArePresent(request)), RESERVATION_ROUTES_NEEDED)
    // The hold counts down to an instant on the API's clock.
    await startBrowserClockWithTheApi(page)
  })

  test('two models are one reservation, a hold is refused and tried again, and nothing unfinished is left in the way', async ({
    page,
    request,
  }, testInfo) => {
    const period = periodStarting(COLLECT_IN_DAYS[testInfo.project.name] ?? DEFAULT_COLLECT_IN_DAYS)
    const branch = await firstBranch(request)
    const made = watchReservationsMade(page)

    await signInAsCustomer(page, SECOND_CUSTOMER_EMAIL)
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

    const first = await addFreeModel(page, branch, period, 0)
    const second = await addFreeModel(page, branch, period, 1)
    expect(
      await branchCanSupply(request, first, branch, period, MOST_OF_ONE_MODEL),
      `${branch.name} can supply ${MOST_OF_ONE_MODEL} of ${first.name}, so this journey cannot ask for more than it has`,
    ).toBe(false)
    await page.getByRole('link', { name: 'Go to my basket' }).click()
    await expect(page.getByRole('heading', { level: 1, name: BASKET_HEADING })).toBeVisible()
    const quantityOfFirst = page
      .getByRole('group', { name: `How many of ${first.name}` })
      .getByLabel('How many', { exact: true })

    // Two models in one basket are one reservation with two lines.
    await page.getByRole('button', { name: REVIEW }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    const lines = page.getByRole('table').getByRole('row')
    await expect(lines).toHaveCount(3)
    await expect(lines.nth(1)).toContainText(first.name)
    await expect(lines.nth(2)).toContainText(second.name)
    expect(await made.references()).toHaveLength(1)

    // Going back and reviewing the same basket carries on with the same draft.
    await page.getByRole('button', { name: CHANGE_BASKET }).click()
    await expect(stepHeading(page, BASKET_STEP)).toBeFocused()
    await page.getByRole('button', { name: REVIEW }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    expect(await made.references()).toHaveLength(1)

    // More of the first model than the branch has. The basket is priced, and
    // the hold is refused in the server's own sentence.
    await page.getByRole('button', { name: CHANGE_BASKET }).click()
    await quantityOfFirst.fill(String(MOST_OF_ONE_MODEL))
    await page.getByRole('button', { name: REVIEW }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    await expect(lines.nth(1)).toContainText(`${MOST_OF_ONE_MODEL} units`)
    const holdAnswer = page.waitForResponse((response) => HOLD_ROUTE.test(new URL(response.url()).pathname))
    await page.getByRole('button', { name: HOLD }).click()
    const refused = await holdAnswer
    expect(refused.status()).toBe(HTTP_CONFLICT)
    const { detail } = (await refused.json()) as { detail: string }
    expect(detail).toContain(first.name)
    const refusal = page.getByRole('alert').filter({ hasText: HOLD_REFUSED })
    await expect(refusal).toContainText(detail)
    await expect(stepHeading(page, REVIEW_STEP)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    // The basket can be changed and tried again.
    await refusal.getByRole('button', { name: CHANGE_BASKET }).click()
    await expect(stepHeading(page, BASKET_STEP)).toBeFocused()
    await quantityOfFirst.fill('1')
    await page.getByRole('button', { name: REVIEW }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    await page.getByRole('button', { name: HOLD }).click()
    await expect(stepHeading(page, HOLD_STEP)).toBeFocused()
    const timer = page.getByRole('timer', { name: 'Time left to confirm' })
    await expect(timer).toHaveText(CLOCK_FACE)

    // A reload in the middle of the hold picks the same reservation up.
    const heldBefore = await page.evaluate<string>(STORED_BASKET)
    await page.reload()
    await expect(stepHeading(page, HOLD_STEP)).toBeVisible()
    await expect(timer).toHaveText(CLOCK_FACE)
    await expect(page.getByRole('button', { name: 'Confirm this hire' })).toBeEnabled()
    expect(await page.evaluate<string>(STORED_BASKET)).toBe(heldBefore)
    expect(await made.references()).toHaveLength(3)

    // Giving the hold up frees the units again.
    await page.getByRole('button', { name: 'Release the hold and change my basket' }).click()
    await expect(stepHeading(page, BASKET_STEP)).toBeFocused()

    // A review the customer walks away from is a booking that was not finished.
    await page.getByRole('button', { name: REVIEW }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    const [firstDraft, refusedDraft, held, unfinished] = await made.references()
    expect(unfinished).toBeDefined()

    // SC-07. The one that was held and released is cancelled, with both models
    // on its one row. The two drafts that were replaced before they held
    // anything are abandoned baskets, and the server leaves them out.
    await page.goto('/reservations')
    await expect(page.getByRole('heading', { level: 1, name: 'My hires' })).toBeVisible()
    const list = page.getByRole('region', { name: 'My bookings' })
    await expect(bookingRow(page, held)).toContainText('Cancelled')
    await expect(bookingRow(page, held)).toContainText(`1 x ${first.name}, 1 x ${second.name}`)
    for (const abandoned of [firstDraft, refusedDraft]) {
      await expect(bookingRow(page, abandoned)).toHaveCount(0)
    }

    // The unfinished one is left out, and the list says that something was.
    await expect(bookingRow(page, unfinished)).toHaveCount(0)
    await expect(list.getByText(/you started and did not finish (is|are) left out of this list/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    // The filter still shows it.
    await list.getByRole('button', { name: /^Show (it|them)/ }).click()
    await expect(page).toHaveURL(/\/reservations\?status=DRAFT$/)
    await expect(page.getByLabel('Filter by status')).toHaveValue('DRAFT')
    await expect(bookingRow(page, unfinished)).toContainText('Not finished')

    // SC-08. It can be cancelled from its own screen, which leaves no draft.
    await bookingRow(page, unfinished).getByRole('link', { name: `View booking ${unfinished}` }).click()
    await expect(page.getByRole('heading', { level: 1, name: unfinished })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel this booking' }).click()
    await page.getByRole('button', { name: 'Yes, cancel this booking' }).click()
    await expect(page.getByText('This booking has been cancelled')).toBeVisible()
  })
})
