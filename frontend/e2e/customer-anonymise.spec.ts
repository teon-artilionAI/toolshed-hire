/**
 * The owner removing a customer's personal details from the customer holds on
 * SC-23 (#113), scanned for accessibility and measured on a phone 360 pixels
 * wide.
 *
 * The owner opens the question, which says what is removed, what stays and
 * that it cannot be undone, gives a reason and confirms. The notice names who
 * the customer was, and the list read again shows them as a former customer
 * with nothing left to do. A customer with a hire still open is refused, and
 * the server's sentence shows under the question. The open question and the
 * answered list are scanned, the states the other owner's questions are
 * scanned in.
 *
 * Like user-management.spec.ts it answers the API itself, from user-answers.ts
 * through admin-answers.ts, so it runs with or without a backend and never
 * depends on what a database holds. The answers here remember the customer
 * once their details are removed, so the list read after it shows them that way.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { openAdminScreen, usersScreen } from './admin-answers.ts'
import { problem } from './answered.ts'
import { blockingViolations } from './axe.ts'
import { NARROW_PHONE, ROUNDING_PIXELS, sidewaysOverflow } from './overflow.ts'
import {
  ANONYMISED_HELD_CUSTOMER,
  CUSTOMERS_AFTER_ANONYMISING,
  HELD_CUSTOMER_ID,
  HELD_CUSTOMER_NAME,
  USER_ANSWERS,
} from './user-answers.ts'

const CUSTOMERS_ROUTE = 'GET /api/admin/customers'
const ANONYMISE_ROUTE = `POST /api/admin/customers/${HELD_CUSTOMER_ID}/anonymise`
const QUESTION = `Anonymise ${HELD_CUSTOMER_NAME}?`
const REASON = 'Asked by email to remove every detail we hold.'
const STILL_OPEN =
  'This customer still has a booking still open and a hire not yet settled, so their details cannot be removed yet. Finish what is open first.'

/** The customers' answers, which remember the customer once anonymised. */
function rememberingAnswers(): Record<string, unknown> {
  let removed = false
  return {
    [CUSTOMERS_ROUTE]: () => (removed ? CUSTOMERS_AFTER_ANONYMISING : USER_ANSWERS[CUSTOMERS_ROUTE]),
    [ANONYMISE_ROUTE]: () => {
      removed = true
      return ANONYMISED_HELD_CUSTOMER
    },
  }
}

/** Open the question for the customer on hold and wait for its heading. */
async function askToAnonymise(page: Page): Promise<void> {
  await page.getByRole('article', { name: HELD_CUSTOMER_NAME }).getByRole('button', { name: /^Anonymise/ }).click()
  await expect(page.getByRole('heading', { level: 4, name: QUESTION })).toBeFocused()
}

/** Give the reason and confirm. */
async function confirmWithAReason(page: Page): Promise<void> {
  const question = page.getByRole('form', { name: QUESTION })
  await question.getByLabel('Why').fill(REASON)
  await question.getByRole('button', { name: 'Yes, anonymise' }).click()
}

test.describe('the owner removes the personal details of a customer', () => {
  test('the question, the notice and the anonymised customer have no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openAdminScreen(page, usersScreen(true), rememberingAnswers())

    await askToAnonymise(page)
    const question = page.getByRole('form', { name: QUESTION })
    await expect(question.getByText(/address and ID digits are removed, and they can no longer sign in\.$/)).toBeVisible()
    await expect(question.getByText('Their hires, charges and deposits are kept for 5 years as financial records.')).toBeVisible()
    await expect(question.getByText('This cannot be undone.')).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    await confirmWithAReason(page)
    await expect(page.getByText(`The personal details of ${HELD_CUSTOMER_NAME} were removed`)).toBeVisible()
    await expect(page.getByText(/^They are listed as Former customer from now on\./)).toBeVisible()
    const former = page.getByRole('article', { name: 'Former customer' })
    await expect(former.getByText(/^Their personal details were removed on .+ 2026\./)).toBeVisible()
    await expect(former.getByRole('button')).toHaveCount(0)
    await expect(page.getByRole('article', { name: HELD_CUSTOMER_NAME })).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])
  })

  test('a customer with something still open is refused with the server sentence, with no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openAdminScreen(page, usersScreen(true), {
      [ANONYMISE_ROUTE]: problem(409, 'state-transition', STILL_OPEN),
    })

    await askToAnonymise(page)
    await confirmWithAReason(page)

    const refusal = page.getByRole('form', { name: QUESTION }).getByRole('alert')
    await expect(refusal).toContainText(`The personal details of ${HELD_CUSTOMER_NAME} were not removed`)
    await expect(refusal).toContainText(STILL_OPEN)
    await expect(page.getByRole('form', { name: QUESTION }).getByLabel('Why')).toHaveValue(REASON)
    expect(await blockingViolations(page)).toEqual([])
  })
})

test.describe('the question before a customer is anonymised on a phone 360 pixels wide', () => {
  test.use({ viewport: NARROW_PHONE })

  test('the question fits, with nothing to scroll sideways', async ({ page }) => {
    await openAdminScreen(page, usersScreen(true))

    await askToAnonymise(page)

    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
})
