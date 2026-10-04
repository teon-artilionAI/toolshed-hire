/**
 * What the booking specs share.
 *
 * The specs name no tool and no branch, because the seed can change. A search
 * is narrowed to the first branch the API lists, and it then holds only the
 * models that are free at that branch for the dates, so a model taken from it
 * can be booked.
 *
 * The database behind the API keeps what a run books. So nothing here expects
 * a clean one. A journey books its own dates, takes a model that is free for
 * them, and knows the reservations it made by the references the API answered
 * with.
 */

import { expect } from '@playwright/test'
import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { dateFromToday } from './hire-dates.ts'

/** Rand as the screens write it, for example "R 1 360,00". */
export const RAND = /R\s[\d\s]+[,.]\d{2}/

/** A booking reference, for example TSH-R-26-000124. */
export const REFERENCE = /TSH-R-\d{2}-\d{6}/

/** Minutes and seconds left on a hold, for example 29:58. */
export const CLOCK_FACE = /^\d{2}:\d{2}$/

export const BASKET_HEADING = 'Your hire basket'
export const BASKET_STEP = 'Check your basket'
export const REVIEW_STEP = 'Step 1 of 3. Review the cost'
export const HOLD_STEP = 'Step 2 of 3. Hold the equipment'
export const CONFIRMED_STEP = 'Step 3 of 3. Your hire is confirmed'

/**
 * What the confirmation says about its email.
 *
 * @param deliverable Whether the session says email can reach the customer.
 */
export function confirmationEmailSentence(deliverable: boolean): RegExp {
  return deliverable
    ? /A confirmation email is on its way to you\./
    : /This demonstration delivers email to one address only, so the confirmation email will not arrive\. The reference TSH-R-\d{2}-\d{6} on this screen is your booking\./
}

/** The one key the page keeps the basket under, in the storage of the tab. */
export const BASKET_KEY = 'toolshed.basket'

/** Reads the basket the page keeps in the storage of the tab. Written as text
 *  because the browser runs it, and these files are compiled without the
 *  browser types. */
export const STORED_BASKET = `window.sessionStorage.getItem('${BASKET_KEY}')`

const HIRE_DAYS = 3
const RESERVATIONS_PATH = '/api/reservations'
const HTTP_CREATED = 201

export interface BranchOnTheWire {
  code: string
  name: string
}

export interface Period {
  from: string
  to: string
}

/** A model that was put in the basket, as the catalogue names it. */
export interface ModelInBasket {
  name: string
  slug: string
}

/**
 * The dates one journey books in one browser project.
 *
 * The browser projects run side by side and so do the journeys, so each books
 * its own dates and none competes with another for a unit.
 *
 * @param collectInDays How many days ahead the hire starts.
 */
export function periodStarting(collectInDays: number): Period {
  return { from: dateFromToday(collectInDays), to: dateFromToday(collectInDays + HIRE_DAYS) }
}

/** The first branch the API lists, through the same address the page uses. */
export async function firstBranch(request: APIRequestContext): Promise<BranchOnTheWire> {
  const answer = await request.get('/api/branches')
  expect(answer.ok(), `the branch route answered ${answer.status()}`).toBe(true)
  const { items } = (await answer.json()) as { items: BranchOnTheWire[] }
  expect(items.length, 'the seeded database has no branch').toBeGreaterThan(0)
  return items[0]
}

export function stepHeading(page: Page, name: string): Locator {
  return page.getByRole('heading', { level: 2, name })
}

/** The figure shown against one term in a list of figures. */
export function figure(page: Page, term: string | RegExp): Locator {
  return page.locator('dt', { hasText: term }).locator('xpath=following-sibling::dd[1]')
}

/**
 * Open a model that is free at a branch for a period, and put one of it in
 * the basket.
 *
 * @param position Which of the free models to take, counted from zero.
 */
export async function addFreeModel(
  page: Page,
  branch: BranchOnTheWire,
  period: Period,
  position = 0,
): Promise<ModelInBasket> {
  await page.goto(`/search?from=${period.from}&to=${period.to}&branch=${branch.code}`)
  const results = page.getByRole('region', { name: 'Search results' })
  await expect(results.getByRole('status').first()).toHaveText(/\d+ models? (is|are) free at /)
  const row = results
    .getByRole('listitem')
    .filter({ has: page.getByRole('heading', { level: 3 }) })
    .nth(position)
  const name = await row.getByRole('heading', { level: 3 }).innerText()
  await row.getByRole('link', { name: /See dates and book/ }).click()

  // SC-03. The basket takes the model only once the branch has said free and
  // the server has priced it, both for these dates.
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
  await expect(page.getByText(`Free at ${branch.name}`)).toBeVisible()
  await expect(page.getByRole('group', { name: 'Price for these dates' })).toBeVisible()
  await page.getByRole('button', { name: 'Add to my hire basket' }).click()
  await expect(page.getByText('Added to your hire basket')).toBeVisible()
  return { name, slug: new URL(page.url()).pathname.split('/').pop() ?? '' }
}

/** The reservations a page has made, for a journey that has to find them again. */
export interface ReservationsMade {
  /** The references so far, oldest first. */
  references: () => Promise<string[]>
}

/**
 * Note the reference of every reservation the page makes from here on.
 *
 * A journey finds its own bookings by these and by nothing else, so what an
 * earlier run left in the database cannot be mistaken for them.
 */
export function watchReservationsMade(page: Page): ReservationsMade {
  const made: Promise<string>[] = []
  page.on('response', (response) => {
    const created =
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === RESERVATIONS_PATH &&
      response.status() === HTTP_CREATED
    if (!created) return
    made.push(response.json().then((body: { reference: string }) => body.reference))
  })
  return { references: () => Promise.all(made) }
}

/** The row of one booking in My Hires, found by its reference. */
export function bookingRow(page: Page, reference: string): Locator {
  return page.getByRole('row').filter({ hasText: reference })
}
