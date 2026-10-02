/**
 * Registration, the account screen and a password reset, against the real
 * backend.
 *
 * There are two journeys here.
 *
 * A visitor registers with an address nobody has used, is told to check their
 * email, signs in with the new account, opens the account screen, is told the
 * address is not confirmed yet, and corrects their phone number. That is
 * SC-05, SC-06 and SC-09 end to end.
 *
 * A visitor asks for a password reset and is shown the one message the screen
 * has for that, which is the same whoever the address belongs to.
 *
 * Both need the registration and account routes. `e2e/backend.ts` asks one of
 * those routes by name, because a healthy backend is not proof that it has
 * them. When they are not there, both journeys skip themselves and the run
 * still passes.
 *
 * Neither journey touches a seeded account. The first makes an account of its
 * own in each browser project, with an address built from the time, so a
 * second run never meets the first one's account. The second asks about an
 * address that has no account at all. Nothing here follows a link from an
 * email, because the address is not one this system delivers to. The
 * component tests cover where the links land, with the network replaced.
 *
 * The API throttles registration and reset requests for one client address.
 * One run makes two of each, one in each browser project.
 */

import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { ACCOUNT_ROUTES_NEEDED, accountRoutesArePresent } from './backend.ts'
import { REGISTER, SIGN_IN } from './routes.ts'

/** The password of the account a run registers. It is at least twelve
 *  characters, which is the rule, and it guards nothing but that account. */
const NEW_ACCOUNT_PASSWORD = 'browser-test-password'

const PROFILE_PATH = '/api/me/profile'
const NEW_PHONE = '083 555 0199'

/** An address nobody has used. The time keeps one run apart from the next,
 *  and the project keeps the two browsers of one run apart. */
function unusedAddress(prefix: string, projectName: string): string {
  return `${prefix}.${projectName}.${Date.now()}@example.com`
}

/** The value shown against one term in the lists of details on SC-09. */
function detail(page: Page, term: string): Locator {
  return page.locator('dt', { hasText: term }).locator('xpath=following-sibling::dd[1]')
}

test.describe('registration and the account screen against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await accountRoutesArePresent(request)), ACCOUNT_ROUTES_NEEDED)
  })

  test('a visitor registers, signs in, is told the address is unconfirmed, and edits their phone number', async ({
    page,
  }, testInfo) => {
    const email = unusedAddress('browser.test', testInfo.project.name)

    // SC-05. The form, sent with exactly what it asks for.
    await page.goto(REGISTER.path)
    await expect(page.getByRole('heading', { level: 1, name: REGISTER.heading })).toBeVisible()
    await page.getByLabel('Full name').fill('Browser Test')
    await page.getByLabel('Email address').fill(email)
    await page.getByLabel('Mobile number').fill('082 441 7719')
    await page.getByLabel('Last four characters of the document number').fill('5083')
    await page.getByLabel('Billing address, first line').fill('12 Loop Street')
    await page.getByLabel('Billing suburb').fill('Gardens')
    await page.getByLabel('Postal code').fill('8001')
    // The first branch the API lists stands in until another is chosen.
    await expect(page.getByLabel('Usual collection branch')).toBeEnabled()
    await page.getByLabel('Password', { exact: true }).fill(NEW_ACCOUNT_PASSWORD)
    await page.getByLabel('Confirm password').fill(NEW_ACCOUNT_PASSWORD)
    await page.getByRole('checkbox', { name: /I have read the privacy notice/ }).check()
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Create my account' }).click()

    // The same words whoever the address belongs to, and focus on the heading.
    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeFocused()
    await expect(page.getByText('If that address is new, we have sent it a link.')).toBeVisible()
    await expect(page.getByText(email)).toBeVisible()
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])

    // SC-06. The new account signs in before its address is confirmed.
    await page.getByRole('link', { name: 'Go to sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
    await page.getByLabel('Email address').fill(email)
    await page.getByLabel('Password', { exact: true }).fill(NEW_ACCOUNT_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

    // SC-09. The profile is the one that was registered, and it says the
    // address is not confirmed yet.
    await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Account' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'My account' })).toBeVisible()
    await expect(page.getByText('Your email address has not been confirmed')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Send the link again' })).toBeVisible()
    await expect(detail(page, 'Name')).toHaveText('Browser Test')
    await expect(detail(page, 'Email address')).toHaveText(email)
    await expect(detail(page, 'South African ID')).toHaveText('Ending 5083')
    await expect(detail(page, 'Account standing')).toHaveText('Good standing')
    await expect(page.getByText('Hires and charges appear here once equipment has been collected.')).toBeVisible()
    expect(await blockingViolations(page)).toEqual([])

    // The phone number is corrected, and the screen shows what the server kept.
    await page.getByRole('button', { name: 'Edit my details' }).click()
    await page.getByLabel('Mobile number').fill(NEW_PHONE)
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' && new URL(response.url()).pathname === PROFILE_PATH,
    )
    await page.getByRole('button', { name: 'Save these details' }).click()
    const answer = await saved
    expect(answer.status()).toBe(200)
    expect(answer.request().postDataJSON()).toEqual({ phone: NEW_PHONE.replaceAll(' ', '') })
    const { phone } = (await answer.json()) as { phone: string }

    await expect(page.getByText('Your details have been updated')).toBeVisible()
    await expect(detail(page, 'Mobile number')).toHaveText(phone)
    await expect(page.getByLabel('Mobile number')).toHaveCount(0)
    expect(await blockingViolations(page)).toEqual([])
  })

  test('a visitor asks for a password reset and sees the one message, whoever the address belongs to', async ({
    page,
  }, testInfo) => {
    const email = unusedAddress('nobody.here', testInfo.project.name)

    await page.goto(SIGN_IN.path)
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
    await page.getByRole('button', { name: 'Forgotten your password?' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Reset your password' })).toBeVisible()

    await page.getByLabel('Email address').fill(email)
    await page.getByRole('button', { name: 'Send me a reset link' }).click()

    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeFocused()
    await expect(
      page.getByText('If that address has an account, we have sent it a link to choose a new password.'),
    ).toBeVisible()
    // Nothing on the screen says whether the address has an account.
    await expect(page.getByRole('main')).not.toContainText(/no account|not registered|does not exist/i)
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Back to sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN.heading })).toBeVisible()
  })
})
