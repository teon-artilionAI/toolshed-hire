/**
 * A booking at the counter, against the real backend.
 *
 * A seeded counter assistant signs in, registers a walk in with a name nobody
 * has used, books one unit for them for today at the assistant's own branch,
 * checks it out and sees the reference of the hire. That is SC-12, SC-13 and
 * SC-14 end to end, through the same routes an online booking uses.
 *
 * It needs the customer and checkout routes, which a healthy backend may not
 * have yet, so `e2e/backend.ts` asks for one of each by name. When they are
 * not there the journey skips itself and the run still passes.
 *
 * Nothing here names a tool. The model is picked through the availability
 * search for the assistant's branch, which lists only what is free there for
 * the dates, so a second run finds a unit the first did not take. Each browser
 * project signs in as the assistant of a different branch, so the two never
 * compete for a unit. A run leaves the unit it checked out on hire, because a
 * return is a later change. The seeded fleet has hundreds of units, so that
 * runs out only after a great many runs.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { COUNTER_ROUTES_NEEDED, counterRoutesArePresent } from './backend.ts'
import { RAND, REFERENCE, figure } from './booking.ts'
import { signInAsStaff, staffFor } from './staff.ts'

/** A hire reference, for example TSH-H-26-000099. */
const RENTAL_REFERENCE = /TSH-H-\d{2}-\d{6}/

const LINES_STEP = 'Step 1 of 4. Choose the dates and the tools'
const REVIEW_STEP = 'Step 2 of 4. Check the cost'
const HELD_STEP = 'Step 3 of 4. Confirm the booking'
const CONFIRMED_STEP = 'Step 4 of 4. The booking is confirmed'
const CHECKOUT_STEP = 'Step 1 of 3. Check each unit and take the deposit'

/** How many digits of the time go into a phone number, after its prefix. */
const PHONE_TIME_DIGITS = 8

/** A full name and a mobile number nobody has used. The time keeps one run
 *  apart from the next, and the project keeps the two browsers of one run apart. */
function unusedWalkIn(projectName: string): { name: string; phone: string } {
  const mobile = projectName.includes('mobile')
  const stamp = String(Date.now())
  return {
    name: `${mobile ? 'Mobile' : 'Desktop'} Walkin${stamp}`,
    phone: `0${mobile ? '7' : '8'}${stamp.slice(-PHONE_TIME_DIGITS)}`,
  }
}

function stepHeading(page: Page, name: string | RegExp): Locator {
  return page.getByRole('heading', { level: 2, name })
}

test.describe('a booking at the counter against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await counterRoutesArePresent(request)), COUNTER_ROUTES_NEEDED)
  })

  test('an assistant registers a walk in, books one unit for today, checks it out and sees the hire', async ({
    page,
  }, testInfo) => {
    const { name, phone } = unusedWalkIn(testInfo.project.name)
    await signInAsStaff(page, staffFor(testInfo.project.name))

    // SC-12. The walk in, registered at the assistant's branch with no login.
    await page.goto('/counter/customers')
    await expect(page.getByRole('heading', { level: 1, name: 'Find a customer' })).toBeVisible()
    await page.getByLabel('Full name').fill(name)
    await page.getByLabel('Mobile number').fill(phone)
    await page.getByLabel('Last four characters of the document number').fill('5083')
    await page.getByLabel('Billing address, first line').fill('12 Loop Street')
    await page.getByLabel('Billing suburb').fill('Gardens')
    await page.getByLabel('Postal code').fill('8001')
    expect(await blockingViolations(page)).toEqual([])
    await page.getByRole('button', { name: 'Add this customer' }).click()

    await expect(stepHeading(page, name)).toBeFocused()
    await expect(page.getByText(`${name} is on file`)).toBeVisible()
    await expect(page.getByText('No login', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: `New booking for ${name}` }).click()

    // SC-13. One unit of the first model free at this branch, for today.
    await expect(page.getByRole('heading', { level: 1, name: 'New booking' })).toBeVisible()
    await expect(stepHeading(page, LINES_STEP)).toBeVisible()
    await expect(page.getByText(new RegExp(`Booking for ${name}`))).toBeVisible()
    const finder = page.getByRole('region', { name: 'Tools free at this branch' })
    await expect(finder.getByRole('status')).toHaveText(/\d+ models? (is|are) free at .+ for these dates\./)
    await finder.getByRole('button', { name: /^Add / }).first().click()
    await expect(page.getByText(/^1 unit free at .+ for these dates$/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Work out the cost' }).click()
    await expect(stepHeading(page, REVIEW_STEP)).toBeFocused()
    await expect(figure(page, 'Total with VAT')).toHaveText(RAND)
    await expect(figure(page, 'Deposit to take at collection')).toHaveText(RAND)

    await page.getByRole('button', { name: 'Hold the equipment' }).click()
    await expect(stepHeading(page, HELD_STEP)).toBeFocused()
    await expect(page.getByText(/^Set aside:/)).toBeVisible()

    await page.getByRole('button', { name: 'Confirm the booking' }).click()
    await expect(stepHeading(page, CONFIRMED_STEP)).toBeFocused()
    const confirmation = page.getByText(new RegExp(`^Booking ${REFERENCE.source} is confirmed$`))
    await expect(confirmation).toBeVisible()
    const reference = REFERENCE.exec(await confirmation.innerText())?.[0] ?? ''
    expect(reference).toMatch(REFERENCE)
    expect(await blockingViolations(page)).toEqual([])

    // SC-14. Every tag read, the agreement signed, asked in words, handed over.
    await page.getByRole('link', { name: 'Check out now' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Checkout and deposit' })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/counter/checkout/${reference}$`))
    await expect(stepHeading(page, CHECKOUT_STEP)).toBeVisible()
    const tags = page.getByRole('checkbox', { name: /I have read the tag on the unit/ })
    for (const tag of await tags.all()) await tag.check()
    await page.getByRole('checkbox', { name: /read the hire agreement and signed it/ }).check()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Check out the equipment' }).click()
    await expect(stepHeading(page, new RegExp(`^Step 2 of 3\\. Hand the equipment over to ${name}\\?$`))).toBeFocused()
    await page.getByRole('button', { name: 'Yes, hand it over' }).click()

    const out = stepHeading(page, /^Step 3 of 3\. The equipment is out on hire TSH-H-\d{2}-\d{6}$/)
    await expect(out).toBeFocused()
    expect(await out.innerText()).toMatch(RENTAL_REFERENCE)
    await expect(page.getByText(/^Hire TSH-H-\d{2}-\d{6} is open$/)).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])
  })
})
