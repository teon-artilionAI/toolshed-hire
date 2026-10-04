/**
 * The owner's audit trail, notification log and charge corrections, against
 * the real backend.
 *
 * A counter assistant books one unit for a new walk in, checks it out and
 * takes it back, so the run has a hire of its own to correct. Then the seeded
 * owner signs in on a browser of their own, reads the audit trail narrowed to
 * bookings, opens the notification log, and on the return screen of that hire
 * reverses the hire charge with a written reason and sees the reversal row.
 * That is SC-24, SC-14 and SC-15 end to end, under the same Content Security
 * Policy a visitor gets.
 *
 * The trail and the log are checked for their shape and not for particular
 * entries, because the other journeys write to both while this one runs. The
 * hire is the run's own, so its charges are known.
 *
 * It needs the admin operations routes, which a healthy backend may not have
 * yet, so `e2e/operations-backend.ts` asks for the trail and the log by name.
 * When they are not there the spec skips itself and the run still passes.
 */

import { expect, test } from '@playwright/test'
import type { Browser, Page, TestInfo } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { bookForTodayAtTheCounter } from './counter-booking.ts'
import { checkOutAndOpenTheHire } from './damage-journey.ts'
import { OPERATIONS_ROUTES_NEEDED, operationsRoutesArePresent } from './operations-backend.ts'
import { signInAsOwner, signInAsStaff, staffFor } from './staff.ts'

const LOG_HEADING = 'Audit and notification log'
const RETURN_HEADING = 'Return and condition inspection'

/** What the owner writes when reversing the hire charge. */
const REVERSAL_REASON = 'Browser test, charged in error'

/** SC-15. Every unit back in the grade it went out at, and the settlement shown. */
async function takeItBackAsItWent(page: Page): Promise<string> {
  const returnAddress = new URL(page.url()).pathname
  await page.getByRole('checkbox', { name: /is back on the counter\. Take it back now\.$/ }).check()
  await page.getByRole('button', { name: 'Take the ticked units back' }).click()
  await page.getByRole('button', { name: 'Yes, take them back' }).click()
  await expect(page.getByText(/^Every unit on TSH-H-\d{2}-\d{6} is back$/)).toBeVisible()
  return returnAddress
}

/** SC-24. The trail narrowed to bookings, then the notification log. */
async function readTheLog(page: Page): Promise<void> {
  await page.goto('/admin/audit')
  await expect(page.getByRole('heading', { level: 1, name: LOG_HEADING })).toBeVisible()
  await expect(page.getByText('Nobody can change this record')).toBeVisible()
  await page.getByLabel('Kind of record').selectOption('reservation')
  await page.getByRole('button', { name: 'Show these events' }).click()
  await expect(page).toHaveURL(/\/admin\/audit\?entityType=reservation$/)
  const events = page.getByRole('region', { name: 'The events' })
  await expect(events.getByRole('status').first()).toHaveText(/^\d+ events? match(es)?, newest first\.$/)
  await expect(events.getByRole('article').first()).toBeVisible()
  await expect(page.getByText('This screen still shows sample data')).toHaveCount(0)
  expect(await blockingViolations(page)).toEqual([])

  await page.getByRole('navigation', { name: 'Parts of the log' }).getByRole('link', { name: 'Notification log' }).click()
  await expect(page).toHaveURL(/\/admin\/audit\?view=notifications$/)
  await expect(page.getByRole('heading', { level: 2, name: 'Notification log' })).toBeFocused()
  const emails = page.getByRole('region', { name: 'The emails' })
  await expect(emails.getByRole('status').first()).toHaveText(/^\d+ emails?, newest first\.$/)
  expect(await blockingViolations(page)).toEqual([])
}

/** SC-15. The hire charge reversed with a reason, and the reversal on the hire. */
async function reverseTheHireCharge(page: Page, returnAddress: string): Promise<void> {
  await page.goto(returnAddress)
  await expect(page.getByRole('heading', { level: 1, name: RETURN_HEADING })).toBeVisible()
  const charges = page.getByRole('list', { name: /^Charges on TSH-H-/ })
  const hire = charges.getByRole('article', { name: 'Hire', exact: true }).first()
  await hire.getByRole('button', { name: /^Reverse the hire charge of / }).click()
  await expect(hire.getByRole('heading', { level: 4, name: /^Reverse the hire charge of .+\?$/ })).toBeFocused()
  await hire.getByLabel('Why').fill(REVERSAL_REASON)
  expect(await blockingViolations(page)).toEqual([])
  await hire.getByRole('button', { name: 'Yes, reverse it' }).click()

  await expect(page.getByText('The hire charge is reversed', { exact: true })).toBeVisible()
  const reversal = charges.getByRole('article').filter({ hasText: /This reverses the hire charge of / })
  await expect(reversal).toHaveCount(1)
  await expect(reversal.getByText(REVERSAL_REASON)).toBeVisible()
  await expect(reversal.getByText(/back to the customer$/)).toBeVisible()
  await expect(hire.getByText('A later charge on this hire reverses this one.')).toBeVisible()
  await expect(hire.getByRole('button', { name: /^Reverse/ })).toHaveCount(0)
  expect(await blockingViolations(page)).toEqual([])
}

/** The owner, on a browser of their own, reads the log and corrects the hire. */
async function ownerCorrects(browser: Browser, testInfo: TestInfo, returnAddress: string): Promise<void> {
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL })
  try {
    const page = await context.newPage()
    await signInAsOwner(page)
    await readTheLog(page)
    await reverseTheHireCharge(page, returnAddress)
  } finally {
    await context.close()
  }
}

test.describe('the owner reads the trail and corrects a hire against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await operationsRoutesArePresent(request)), OPERATIONS_ROUTES_NEEDED)
  })

  test('the owner reads the trail by booking and the log, and reverses the hire charge of a hire just taken back', async ({
    page,
    browser,
  }, testInfo) => {
    await signInAsStaff(page, staffFor(testInfo.project.name))
    await bookForTodayAtTheCounter(page, testInfo.project.name, 'correction')
    await checkOutAndOpenTheHire(page)
    const returnAddress = await takeItBackAsItWent(page)

    await ownerCorrects(browser, testInfo, returnAddress)
  })
})
