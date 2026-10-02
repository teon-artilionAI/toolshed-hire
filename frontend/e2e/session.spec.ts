/**
 * The session, against the real backend.
 *
 * A seeded customer signs in with their own email address and password, stays
 * signed in across a reload, is refused a counter screen, signs out, and is
 * then asked to sign in before a protected screen opens. That is the session
 * from end to end, through the real API and its refresh cookie, under the same
 * Content Security Policy a visitor gets.
 *
 * There is no spec for a wrong password here. A refused attempt counts towards
 * the limit the API keeps on the account, and a browser test that ran often
 * enough would lock the seeded customer out of the specs beside it. The
 * component tests cover every refusal with the network replaced.
 *
 * This file signs the customer in four times in a run, twice in each browser
 * project, and reservation.spec.ts signs them in twice more. The API counts
 * every attempt for an email address, the ones that succeed as well, and
 * allows ten in a fixed window of fifteen minutes. So a second run inside one
 * window is answered 429, and the sign in here then never leaves its screen.
 * The reservation specs sign the other seeded customer in four times, which
 * is counted against that address and not this one.
 *
 * These specs skip themselves when the backend is not there or does not have
 * the session routes, so the run still passes. `e2e/backend.ts` asks one of
 * those routes by name, because a healthy backend is not proof that it has
 * them.
 *
 * The customer and the password are in `e2e/customer.ts`. The password is
 * never written down. It comes from `E2E_CUSTOMER_PASSWORD`, and falls back to
 * the password the development seed uses.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { blockingViolations } from './axe.ts'
import { SESSION_ROUTES_NEEDED, sessionRoutesArePresent } from './backend.ts'
import { signInAsCustomer, submitCustomerSignIn } from './customer.ts'
import { CATALOGUE_HOME, SIGN_IN } from './routes.ts'

const MY_HIRES = { path: '/reservations', heading: 'My hires' }
const COUNTER = { path: '/counter', heading: 'Today at the counter' }
const NO_ACCESS_HEADING = 'You do not have access to this screen'

/** Reads everything the page has put in web storage. Written as text because
 *  the browser runs it, and this file is compiled without the browser types. */
const WEB_STORAGE = 'JSON.stringify([{ ...window.localStorage }, { ...window.sessionStorage }])'

/** The one thing a signed in page keeps there. It is the mark that this
 *  browser may hold a session, from `src/shared/session-markers.ts`, and it is
 *  a fixed word. Nothing else may be stored, and above all no token. */
const STORED_WHILE_SIGNED_IN = JSON.stringify([{ 'toolshed.session-hint': 'yes' }, {}])

/** A signed out page keeps nothing at all. */
const NOTHING_STORED = JSON.stringify([{}, {}])

async function expectHeading(page: Page, name: string): Promise<void> {
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
}

test.describe('the session against the real backend', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await sessionRoutesArePresent(request)), SESSION_ROUTES_NEEDED)
  })

  test('a customer signs in, survives a reload, is refused the counter, and signs out', async ({
    page,
  }) => {
    await signInAsCustomer(page)

    // A customer lands on the catalogue, and the header offers the way out.
    await expect(page).toHaveURL(/\/$/)
    await expectHeading(page, CATALOGUE_HOME.heading)
    const signOut = page.getByRole('button', { name: 'Sign out' })
    await expect(signOut).toBeVisible()

    // The access token is in memory only. Web storage holds one fixed mark.
    expect(await page.evaluate<string>(WEB_STORAGE)).toBe(STORED_WHILE_SIGNED_IN)

    // A reload throws the token away. The refresh cookie brings the session back.
    await page.reload()
    await expectHeading(page, CATALOGUE_HOME.heading)
    await expect(signOut).toBeVisible()

    // A screen that needs a customer account opens.
    await page.goto(MY_HIRES.path)
    await expectHeading(page, MY_HIRES.heading)
    await expect(page).toHaveURL(new RegExp(`${MY_HIRES.path}$`))

    // A counter screen does not. The customer is told so, and is not shown it.
    await page.goto(COUNTER.path)
    await expectHeading(page, NO_ACCESS_HEADING)
    await expect(page.getByRole('heading', { name: COUNTER.heading })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Go to my home screen' })).toHaveAttribute('href', '/')
    expect(await blockingViolations(page)).toEqual([])

    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page).toHaveURL(/\/$/)
    await expectHeading(page, CATALOGUE_HOME.heading)
    await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible()
    await expect.poll(() => page.evaluate<string>(WEB_STORAGE)).toBe(NOTHING_STORED)

    // Signed out means signed out. A reload does not bring the session back.
    await page.reload()
    await expectHeading(page, CATALOGUE_HOME.heading)
    await expect(page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible()

    // And the counter now asks for a sign in, like any protected screen.
    await page.goto(COUNTER.path)
    await expectHeading(page, SIGN_IN.heading)
    await expect(page).toHaveURL(/\/signin\?next=%2Fcounter$/)
  })

  test('a signed out visitor is sent to sign in and brought back afterwards', async ({ page }) => {
    await page.goto(MY_HIRES.path)

    await expectHeading(page, SIGN_IN.heading)
    await expect(page).toHaveURL(/\/signin\?next=%2Freservations$/)
    await submitCustomerSignIn(page)

    await expectHeading(page, MY_HIRES.heading)
    await expect(page).toHaveURL(new RegExp(`${MY_HIRES.path}$`))
  })
})
