/**
 * The counter journey of the release, for the seeded trade customer.
 *
 * A counter assistant finds the seeded trade customer on SC-12 and books one
 * unit for today on SC-13. When the API takes today, the unit is checked out
 * on SC-14 and taken straight back on SC-15 in the condition it went out in,
 * and the deposit is released in full with nothing due. That is the journey.
 *
 * Staging runs on the real clock, and a branch refuses a booking for today
 * once it has closed. Then the journey books two days ahead instead, confirms
 * it, and the customer cancels it from their own SC-08, because the counter
 * screens offer no cancellation of a confirmed booking. It is two days and not
 * one because a confirmed booking cancelled after 17:00 on the day before
 * collection counts as a late cancellation against the customer (BR-16), and
 * the branch closes at 17:00, so cancelling tomorrow's booking then would
 * leave a mark on the customer's record. The journey says which way it went
 * in the output of the run.
 *
 * Either way the customer is left as they were found, with one more booking
 * in their history. Nothing here registers a walk in, so the run adds no
 * customer to staging. The model is the fifth from the end of the first page
 * free at the branch, so it never takes the unit the other counter journeys
 * of a local run take, see counter-booking.ts.
 */

import { expect } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'
import { RAND, REFERENCE, figure } from './booking.ts'
import { signInAsCustomer } from './customer.ts'
import { dateFromToday } from './hire-dates.ts'
import { note } from './staging.ts'

/** The trade customer the seed creates, in `backend/seeding/people.py`. */
export const TRADE_CUSTOMER_EMAIL = 'w.adonis@buildright.co.za'
export const TRADE_CUSTOMER_NAME = 'Wesley Adonis'

/** Counted back from the end of the models free at the branch. */
const MODELS_FROM_THE_END = 5

/** What the API says about today once the branch has closed (BR-04). */
const CLOSED_FOR_TODAY = 'The branch has closed for today. The earliest a hire can start is tomorrow.'

/** How far ahead the booking goes when today is refused, and how long it runs. */
const DAYS_AHEAD_WHEN_CLOSED = 2
const HIRE_DAYS = 1

const LINES_STEP = 'Step 1 of 4. Choose the dates and the tools'
const REVIEW_STEP = 'Step 2 of 4. Check the cost'
const HELD_STEP = 'Step 3 of 4. Confirm the booking'
const CONFIRMED_STEP = 'Step 4 of 4. The booking is confirmed'
const CHECKOUT_STEP = 'Step 1 of 3. Check each unit and take the deposit'
const RETURN_HEADING = 'Return and condition inspection'
const CANCEL_REASON = 'Booked by the release journey on staging'

/** How the journey ended. */
export type CounterOutcome = 'out and back today' | 'booked ahead and cancelled'

function stepHeading(page: Page, name: string | RegExp) {
  return page.getByRole('heading', { level: 2, name })
}

/** SC-12. The trade customer found by their email address, and a new booking started for them. */
async function startABookingForTheTradeCustomer(page: Page): Promise<void> {
  await page.goto('/counter/customers')
  await expect(page.getByRole('heading', { level: 1, name: 'Find a customer' })).toBeVisible()
  await page.getByLabel('Search customers').fill(TRADE_CUSTOMER_EMAIL)
  const found = page.getByRole('region', { name: 'Customers found' })
  await found.getByRole('link', { name: `New booking for ${TRADE_CUSTOMER_NAME}` }).first().click()
  await expect(page.getByRole('heading', { level: 1, name: 'New booking' })).toBeVisible()
  await expect(stepHeading(page, LINES_STEP)).toBeVisible()
  await expect(page.getByText(new RegExp(`Booking for ${TRADE_CUSTOMER_NAME}`))).toBeVisible()
}

/** SC-13. One unit of a model free at the branch for the dates on the screen. */
async function addOneFreeUnit(page: Page): Promise<void> {
  const finder = page.getByRole('region', { name: 'Tools free at this branch' })
  const freeModels = /^\d+ models? (is|are) free at .+ for these dates\.$/
  await expect(finder.getByRole('status').filter({ hasText: freeModels })).toBeVisible()
  const addButtons = finder.getByRole('button', { name: /^Add / })
  const freeCount = await addButtons.count()
  expect(freeCount, 'the branch needs a free model for the dates').toBeGreaterThan(0)
  await addButtons.nth(Math.max(0, freeCount - MODELS_FROM_THE_END)).click()
  await expect(page.getByText(/^1 unit free at .+ for these dates$/)).toBeVisible()
}

/** SC-13. Priced, held and confirmed, and the reference the API gave it. */
async function holdAndConfirm(page: Page): Promise<string> {
  await page.getByRole('button', { name: 'Hold the equipment' }).click()
  await expect(stepHeading(page, HELD_STEP)).toBeFocused()
  await page.getByRole('button', { name: 'Confirm the booking' }).click()
  await expect(stepHeading(page, CONFIRMED_STEP)).toBeFocused()
  const confirmation = page.getByText(new RegExp(`^Booking ${REFERENCE.source} is confirmed$`))
  const reference = REFERENCE.exec(await confirmation.innerText())?.[0] ?? ''
  expect(reference).toMatch(REFERENCE)
  return reference
}

/** The amount on one line of the deposit settlement on SC-15. */
async function settlementAmount(page: Page, line: string): Promise<string> {
  const row = page.getByRole('row', { name: new RegExp(`^${line}`) })
  await expect(row).toBeVisible()
  return RAND.exec(await row.innerText())?.[0] ?? ''
}

/** SC-14 and SC-15. Out on hire, straight back as it went, and the deposit released in full. */
async function checkOutAndTakeBack(page: Page, reference: string): Promise<void> {
  await page.getByRole('link', { name: 'Check out now' }).click()
  await expect(page).toHaveURL(new RegExp(`/counter/checkout/${reference}$`))
  await expect(stepHeading(page, CHECKOUT_STEP)).toBeVisible()
  for (const tag of await page.getByRole('checkbox', { name: /I have read the tag on the unit/ }).all()) await tag.check()
  await page.getByRole('checkbox', { name: /read the hire agreement and signed it/ }).check()
  await page.getByRole('button', { name: 'Check out the equipment' }).click()
  await page.getByRole('button', { name: 'Yes, hand it over' }).click()
  await expect(stepHeading(page, /^Step 3 of 3\. The equipment is out on hire TSH-H-\d{2}-\d{6}$/)).toBeFocused()

  await page.getByRole('link', { name: 'Open the hire' }).click()
  await expect(page.getByRole('heading', { level: 1, name: RETURN_HEADING })).toBeVisible()
  await page.getByRole('checkbox', { name: /is back on the counter\. Take it back now\.$/ }).check()
  await page.getByRole('button', { name: 'Take the ticked units back' }).click()
  await expect(stepHeading(page, `Take these units back from ${TRADE_CUSTOMER_NAME}?`)).toBeFocused()
  await page.getByRole('button', { name: 'Yes, take them back' }).click()

  await expect(page.getByText(/^Every unit on TSH-H-\d{2}-\d{6} is back$/)).toBeVisible()
  await expect(page.getByText(/was released in full\. Nothing is due\.$/)).toBeVisible()
  const held = await settlementAmount(page, 'Deposit held at collection')
  expect(held).toMatch(RAND)
  expect(await settlementAmount(page, 'Released to the customer')).toBe(held)
  expect(await settlementAmount(page, 'Withheld from the deposit')).toMatch(/^R\s0[,.]00$/)
  expect(await settlementAmount(page, 'Balance due')).toMatch(/^R\s0[,.]00$/)
}

/** SC-08, as the customer on a browser of their own. The booking cancelled with a reason. */
async function customerCancels(browser: Browser, baseURL: string | undefined, reference: string): Promise<void> {
  const context = await browser.newContext({ baseURL })
  try {
    const page = await context.newPage()
    await signInAsCustomer(page, TRADE_CUSTOMER_EMAIL)
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
    await page.goto(`/reservations/${reference}`)
    await expect(page.getByRole('heading', { level: 1, name: reference })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel this booking' }).click()
    await expect(page.getByRole('heading', { name: `Cancel ${reference}?` })).toBeFocused()
    await page.getByLabel(/Why are you cancelling/).fill(CANCEL_REASON)
    await page.getByRole('button', { name: 'Yes, cancel this booking' }).click()
    await expect(page.getByText('This booking has been cancelled')).toBeVisible()
  } finally {
    await context.close()
  }
}

/**
 * Book one unit for the trade customer at the assistant's branch, and finish
 * the booking the way the clock allows.
 *
 * The assistant must already be signed in.
 *
 * @param baseURL The address the project runs against, for the customer's own browser.
 * @returns Which way the journey went.
 */
export async function bookForTheTradeCustomer(page: Page, browser: Browser, baseURL: string | undefined): Promise<CounterOutcome> {
  await startABookingForTheTradeCustomer(page)
  await addOneFreeUnit(page)
  await page.getByRole('button', { name: 'Work out the cost' }).click()

  const review = stepHeading(page, REVIEW_STEP)
  // The sentence can show under the date and in the box above the button.
  const closed = page.getByText(CLOSED_FOR_TODAY).first()
  await expect(review.or(closed)).toBeVisible()

  if (await review.isVisible()) {
    await expect(figure(page, 'Total with VAT')).toHaveText(RAND)
    const reference = await holdAndConfirm(page)
    await checkOutAndTakeBack(page, reference)
    note(`The counter booked ${reference} for today, checked it out and took it straight back with the deposit released in full.`)
    return 'out and back today'
  }

  const from = dateFromToday(DAYS_AHEAD_WHEN_CLOSED)
  note(
    `The branch has closed for today, so the counter books ${from} instead, confirms it, and the customer ` +
      'cancels it. Two days ahead and not one, so the cancellation is not a late one.',
  )
  await page.getByLabel('Goes out on').fill(from)
  await page.getByLabel('Comes back on').fill(dateFromToday(DAYS_AHEAD_WHEN_CLOSED + HIRE_DAYS))
  await expect(page.getByText(/^1 unit free at .+ for these dates$/)).toBeVisible()
  await page.getByRole('button', { name: 'Work out the cost' }).click()
  await expect(review).toBeFocused()
  const reference = await holdAndConfirm(page)
  await expect(page.getByText(/^It goes out on .+\. Check it out from the customer's bookings on that day\.$/)).toBeVisible()
  await customerCancels(browser, baseURL, reference)
  note(`The customer cancelled ${reference} before 17:00 on the day before collection, so it was not a late cancellation.`)
  return 'booked ahead and cancelled'
}
