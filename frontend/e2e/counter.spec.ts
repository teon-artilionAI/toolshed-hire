/**
 * A booking at the counter and its return, against the real backend.
 *
 * A seeded counter assistant signs in, registers a walk in with a name nobody
 * has used, books one unit for them for today at the assistant's own branch,
 * checks it out and sees the reference of the hire. Then they open the hire
 * from the checkout, take the unit back the same day in the condition it went
 * out in, and see the deposit released in full with nothing due. That is
 * SC-12, SC-13, SC-14 and SC-15 end to end, through the same routes an online
 * booking uses. A second journey signs a seeded customer in and finds the hire
 * history on SC-09.
 *
 * The API refuses a booking that starts today once the branch has closed for
 * the day. In the browser tests the API runs with a clock pinned inside
 * business hours, so the booking for today goes out and comes back on the
 * same day whenever the run happens.
 *
 * A third journey checks a second hire out, takes it back one grade worse,
 * sees the deposit waiting for a damage report, files a chargeable report
 * under the cap on SC-16 and sees the deposit settled with the recovery
 * withheld. The owner then resolves the report, so the unit goes back on the
 * shelf. Its steps are in `e2e/damage-journey.ts`.
 *
 * It needs the customer, checkout and returns routes, which a healthy backend
 * may not have yet, so `e2e/backend.ts` asks for each of them by name. When
 * they are not there the journeys skip themselves and the run still passes.
 * The damage journey also needs the damage routes, and `e2e/damage-backend.ts`
 * asks for those.
 *
 * Nothing here names a tool. The model is picked through the availability
 * search for the assistant's branch, which lists only what is free there for
 * the dates, so a second run finds a unit the first did not take. It is the
 * last model on the first page, because the customer journeys take the first
 * ones at Bellville and a unit out on hire is taken for every date. Each browser
 * project signs in as the assistant of a different branch, so the two never
 * compete for a unit. The unit goes back on the shelf at the end of the run, so
 * the next run can take it again.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { RETURN_ROUTES_NEEDED, returnRoutesArePresent } from './backend.ts'
import { RAND, REFERENCE, figure } from './booking.ts'
import { bookForTodayAtTheCounter } from './counter-booking.ts'
import { SECOND_CUSTOMER_EMAIL, signInAsCustomer } from './customer.ts'
import { DAMAGE_ROUTES_NEEDED, damageRoutesArePresent } from './damage-backend.ts'
import {
  checkOutAndOpenTheHire,
  fileAChargeableReport,
  ownerResolves,
  seeTheRecoveryWithheld,
  takeItBackWorse,
} from './damage-journey.ts'
import { signInAsStaff, staffFor } from './staff.ts'

/** A hire reference, for example TSH-H-26-000099. */
const RENTAL_REFERENCE = /TSH-H-\d{2}-\d{6}/

const LINES_STEP = 'Step 1 of 4. Choose the dates and the tools'
const REVIEW_STEP = 'Step 2 of 4. Check the cost'
const HELD_STEP = 'Step 3 of 4. Confirm the booking'
const CONFIRMED_STEP = 'Step 4 of 4. The booking is confirmed'
const CHECKOUT_STEP = 'Step 1 of 3. Check each unit and take the deposit'
const RETURN_HEADING = 'Return and condition inspection'

/** The amount on one line of the deposit settlement on SC-15. */
async function settlementAmount(page: Page, line: string): Promise<string> {
  const row = page.getByRole('row', { name: new RegExp(`^${line}`) })
  await expect(row).toBeVisible()
  return RAND.exec(await row.innerText())?.[0] ?? ''
}

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

test.describe('a booking at the counter and its return against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await returnRoutesArePresent(request)), RETURN_ROUTES_NEEDED)
  })

  test('an assistant registers a walk in, books one unit for today, checks it out and takes it back', async ({
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
    const bookings = page.getByRole('region', { name: `Bookings for ${name}` })
    await expect(bookings.getByText(/^No bookings at .+ yet\.$/)).toBeVisible()
    const customerAddress = page.url()

    // The lookup finds the new customer by name, through the server's search.
    await page.getByLabel('Search customers').fill(name)
    const found = page.getByRole('region', { name: 'Customers found' })
    await expect(found.getByRole('status').first()).toHaveText(`1 customer matches "${name}". The best match is first.`)
    await page.getByRole('link', { name: `New booking for ${name}` }).first().click()

    // SC-13. One unit of the first model free at this branch, for today.
    await expect(page.getByRole('heading', { level: 1, name: 'New booking' })).toBeVisible()
    await expect(stepHeading(page, LINES_STEP)).toBeVisible()
    await expect(page.getByText(new RegExp(`Booking for ${name}`))).toBeVisible()
    // The seeded catalogue fills more than one page, so the page controls have
    // a status of their own. The one that counts the models is the one read here.
    const finder = page.getByRole('region', { name: 'Tools free at this branch' })
    const freeModels = /^\d+ models? (is|are) free at .+ for these dates\.$/
    await expect(finder.getByRole('status').filter({ hasText: freeModels })).toBeVisible()
    // The customer journeys run at the same time and book the first two free
    // models at Bellville for later dates. The API counts a unit that is out
    // on hire as taken for every date, so this journey takes the last model on
    // the page and never the unit a customer journey has just found free.
    await finder.getByRole('button', { name: /^Add / }).last().click()
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

    // SC-15. The hire, opened from the checkout by its key. The unit is not
    // late, so there is no fee, and it comes back at the grade it went out at.
    await page.getByRole('link', { name: 'Open the hire' }).click()
    await expect(page.getByRole('heading', { level: 1, name: RETURN_HEADING })).toBeVisible()
    await expect(page).toHaveURL(/\/counter\/return\/[0-9a-f-]{36}$/)
    await expect(page.getByText(/^Every unit on TSH-H-\d{2}-\d{6} is still out$/)).toBeVisible()
    await expect(page.getByText('Not late. If it comes back today there is no late fee.')).toBeVisible()
    await page.getByRole('checkbox', { name: /is back on the counter\. Take it back now\.$/ }).check()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Take the ticked units back' }).click()
    await expect(stepHeading(page, `Take these units back from ${name}?`)).toBeFocused()
    await expect(page.getByText('Nothing coming back is late, so there is no late fee.')).toBeVisible()
    await page.getByRole('button', { name: 'Yes, take them back' }).click()

    // The last unit is back, so the server settled the deposit with the
    // return. All of it is released and nothing is due.
    await expect(page.getByText(/^Every unit on TSH-H-\d{2}-\d{6} is back$/)).toBeVisible()
    await expect(page.getByText(/was released in full\. Nothing is due\.$/)).toBeVisible()
    const held = await settlementAmount(page, 'Deposit held at collection')
    expect(held).toMatch(RAND)
    expect(await settlementAmount(page, 'Released to the customer')).toBe(held)
    expect(await settlementAmount(page, 'Withheld from the deposit')).toMatch(/^R\s0[,.]00$/)
    expect(await settlementAmount(page, 'Balance due')).toMatch(/^R\s0[,.]00$/)
    await expect(page.getByText('Back and settled', { exact: true })).toBeVisible()
    await expect(page.getByRole('checkbox')).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    // Back on SC-12 the booking is listed at this branch, returned, and
    // offers no second checkout.
    await page.goto(customerAddress)
    await expect(bookings.getByText(reference, { exact: true })).toBeVisible()
    await expect(bookings.getByRole('button', { name: /^At / }).first()).toHaveAttribute('aria-pressed', 'true')
    await expect(bookings.getByText('Returned', { exact: true })).toBeVisible()
    await expect(bookings.getByRole('link', { name: /Check out/ })).toHaveCount(0)
  })

  test('a customer opens their account and finds the hire history', async ({ page }) => {
    await signInAsCustomer(page, SECOND_CUSTOMER_EMAIL)
    // The sign in has to finish before the page is left, or the refresh cookie
    // it sets is lost with the request and the account asks for a sign in.
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

    // SC-09. The history is read from the API and says how many hires there
    // are, or that there are none yet. No tag is ever shown to a customer.
    await page.goto('/account')
    await expect(page.getByRole('heading', { level: 1, name: 'My account' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Hire history and charges' })).toBeVisible()
    const history = page.getByRole('region', { name: 'Your hires' })
    await expect(
      history.getByRole('status').filter({ hasText: /^(You have no hires yet\.|\d+ hires? on your account, newest first\.)$/ }),
    ).toBeVisible()
    await expect(history.getByText(/TSH-[A-Z]{2}-\d{4}/)).toHaveCount(0)
    await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])
  })
})

test.describe('a second hire that comes back damaged, against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await damageRoutesArePresent(request)), DAMAGE_ROUTES_NEEDED)
  })

  test('an assistant takes a hire back a grade worse, files a chargeable report and sees the recovery withheld', async ({
    page,
    browser,
  }, testInfo) => {
    await signInAsStaff(page, staffFor(testInfo.project.name))
    await bookForTodayAtTheCounter(page, testInfo.project.name, 'damage')

    await checkOutAndOpenTheHire(page)
    const tag = await takeItBackWorse(page)
    const reference = await fileAChargeableReport(page, tag)
    await seeTheRecoveryWithheld(page)

    await ownerResolves(browser, testInfo, tag, reference)
  })
})
