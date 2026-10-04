/**
 * The owner's staff accounts and customer holds on SC-23 with their forms and
 * questions open, scanned for accessibility and measured on a phone 360
 * pixels wide.
 *
 * The two views are scanned and measured loaded in accessibility.spec.ts and
 * narrow-screens.spec.ts, from the list of the owner's screens they share.
 * What a person opens on top of them is checked here, so neither of those
 * files grows past a size that can be read in one sitting. The new account
 * form holding back its problem, an account open with its form, and its
 * deactivation asking why, and the question before a customer's hold is
 * released or a customer is blacklisted.
 *
 * Like those two specs it answers the API itself from user-answers.ts, through
 * admin-answers.ts, so it runs with or without a backend and never depends on
 * what a database holds.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { openAdminScreen, usersScreen } from './admin-answers.ts'
import { blockingViolations } from './axe.ts'
import { NARROW_PHONE, ROUNDING_PIXELS, sidewaysOverflow } from './overflow.ts'
import { HELD_CUSTOMER_NAME, LOCKED_ACCOUNT_NAME } from './user-answers.ts'

/** Opens the new account form and presses the button with nothing filled in. */
async function holdBackANewAccount(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Add a staff account' }).click()
  await page.getByRole('form', { name: 'The new staff account' }).getByRole('button', { name: 'Create the account' }).click()
  await expect(page.getByText(/Nothing has been saved yet\. 1 answer needs fixing\./)).toBeVisible()
}

test.describe('the staff accounts and customer holds with their forms and questions open', () => {
  test('the new account form and an account being deactivated have no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openAdminScreen(page, usersScreen(false))

    await holdBackANewAccount(page)
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: `Open the account of ${LOCKED_ACCOUNT_NAME}` }).click()
    await expect(page.getByRole('heading', { level: 3, name: `Account of ${LOCKED_ACCOUNT_NAME}` })).toBeFocused()
    await page.getByRole('button', { name: 'Deactivate the account' }).click()
    await page.getByRole('button', { name: 'Yes, deactivate it' }).click()
    await expect(page.getByText('Write the reason, so whoever reads the audit trail later knows why.')).toBeVisible()

    expect(await blockingViolations(page)).toEqual([])
  })

  test('the question before a hold is released has no serious or critical accessibility violations', async ({ page }) => {
    await openAdminScreen(page, usersScreen(true))

    await page.getByRole('article', { name: HELD_CUSTOMER_NAME }).getByRole('button', { name: /^Release the hold/ }).click()
    await expect(page.getByRole('heading', { level: 4, name: `Release the hold on ${HELD_CUSTOMER_NAME}?` })).toBeFocused()

    expect(await blockingViolations(page)).toEqual([])
  })
})

test.describe('the staff accounts and customer holds on a phone 360 pixels wide', () => {
  test.use({ viewport: NARROW_PHONE })

  test('an account, its form, its question and the new account form fit, with nothing to scroll sideways', async ({ page }) => {
    await openAdminScreen(page, usersScreen(false))

    await page.getByRole('button', { name: `Open the account of ${LOCKED_ACCOUNT_NAME}` }).click()
    await page.getByRole('button', { name: 'Change the name, phone, role or branch' }).click()
    await expect(page.getByRole('form', { name: `The details of ${LOCKED_ACCOUNT_NAME}` })).toBeVisible()
    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await page.getByRole('button', { name: 'Keep the account as it is' }).click()
    await page.getByRole('button', { name: 'Deactivate the account' }).click()
    await expect(page.getByRole('heading', { level: 4, name: `Deactivate the account of ${LOCKED_ACCOUNT_NAME}?` })).toBeVisible()
    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await holdBackANewAccount(page)
    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })

  test('a customer with the question before blacklisting fits, with nothing to scroll sideways', async ({ page }) => {
    await openAdminScreen(page, usersScreen(true))

    await page.getByRole('article', { name: HELD_CUSTOMER_NAME }).getByRole('button', { name: /^Blacklist/ }).click()
    await expect(page.getByRole('heading', { level: 4, name: `Blacklist ${HELD_CUSTOMER_NAME}?` })).toBeVisible()

    expect(await sidewaysOverflow(page)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
})
