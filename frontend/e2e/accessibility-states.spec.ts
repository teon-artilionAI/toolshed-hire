/**
 * Automated accessibility checks for the states a screen moves into, beyond
 * the loaded screens accessibility.spec.ts scans.
 *
 * Signing in refused, asking for a reset link and being told it cannot reach
 * the address, and choosing a new password with its problems showing on
 * SC-06. The registration form holding back its problems, the answer that
 * the link cannot reach the address, and an address confirmed from its link
 * on SC-05. A booking reviewed, held and confirmed on SC-04, where the
 * confirmation says plainly that its email will not arrive. Then the empty
 * and failed states the screens show when there is nothing to list or the
 * API is down, on the customer's, the counter's and the owner's screens.
 *
 * The API is answered by the spec itself, from customer-answers.ts,
 * counter-answers.ts and admin-answers.ts, with the answer each state needs
 * put in place of the shared one. Every scan writes how many findings of each
 * impact it had to the output of the run, and fails on any that is serious or
 * critical.
 */

import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { ADMIN_SCREENS, openAdminScreen } from './admin-answers.ts'
import { Answered, problem } from './answered.ts'
import { reportedViolations } from './axe.ts'
import { openCounterScreen } from './counter-answers.ts'
import { BOOKING_REFERENCE, customerScreen, openCustomerScreen } from './customer-answers.ts'
import { availabilityOf } from './public-answers.ts'

/** A password long enough for the rules of the forms. */
const TYPED_PASSWORD = 'a-long-enough-password-2026'

/** A page of a list with nothing on it. */
function emptyPage(pageSize: number) {
  return { items: [], page: 1, pageSize, total: 0 }
}

/** The API down, the way the proxy answers when the backend is not there. */
const API_DOWN = problem(503, 'service-unavailable', 'The service is not available.')

/** Scan the page and fail on anything serious or critical. */
async function expectClean(page: Page, what: string): Promise<void> {
  expect(await reportedViolations(page, what)).toEqual([])
}

test.describe('signing in and resetting a password', () => {
  test('a refused sign in has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, customerScreen('SC-06'), {
      'POST /api/auth/login': problem(401, 'invalid-credentials', 'Sign in refused.'),
    })
    await page.getByLabel('Email address').fill('w.adonis@buildright.co.za')
    await page.getByLabel('Password', { exact: true }).fill(TYPED_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(page.getByText('We could not sign you in')).toBeVisible()

    await expectClean(page, 'SC-06 with the sign in refused')
  })

  test('a reset link asked for, which cannot reach the address, has no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openCustomerScreen(page, customerScreen('SC-06'))
    await page.getByRole('button', { name: 'Forgotten your password?' }).click()
    await expect(page.getByRole('button', { name: 'Send me a reset link' })).toBeVisible()
    await expectClean(page, 'SC-06 asking for a reset link')

    await page.getByLabel('Email address').fill('w.adonis@buildright.co.za')
    await page.getByRole('button', { name: 'Send me a reset link' }).click()
    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
    await expect(page.getByText('The link cannot reach this address')).toBeVisible()
    await expectClean(page, 'SC-06 with the reset link that cannot reach the address')
  })

  test('a new password from a link, with its problems, has no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openCustomerScreen(page, {
      ...customerScreen('SC-06'),
      path: '/signin#reset=a-reset-token',
      heading: 'Choose a new password',
      loaded: 'Confirm new password',
    })
    await page.getByRole('button', { name: 'Change my password' }).click()
    await expectClean(page, 'SC-06 choosing a new password with its problems showing')
  })
})

test.describe('registering', () => {
  test('the form holding back every problem has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, customerScreen('SC-05'))
    await page.getByRole('button', { name: 'Create my account' }).click()
    await expect(page.getByText(/We cannot open the account yet\. \d+ answers need fixing\./)).toBeVisible()

    await expectClean(page, 'SC-05 with every problem showing')
  })

  test('the answer for an address the link cannot reach has no serious or critical accessibility violations', async ({
    page,
  }) => {
    await openCustomerScreen(page, customerScreen('SC-05'))
    await page.getByLabel('Full name').fill('Thandiwe Nomvula Mokoena-Hendricks')
    await page.getByLabel('Email address').fill('thandiwe.mokoena-hendricks@buildright-construction.co.za')
    await page.getByLabel('Mobile number').fill('082 441 7719')
    await page.getByLabel('Last four characters of the document number').fill('5083')
    await page.getByLabel('Billing address, first line').fill('12 Loop Street, Unit 4, Montague Gardens Industrial Park')
    await page.getByLabel('Billing suburb').fill('Gardens')
    await page.getByLabel('Postal code').fill('8001')
    await expect(page.getByLabel('Usual collection branch')).toBeEnabled()
    await page.getByLabel('Password', { exact: true }).fill(TYPED_PASSWORD)
    await page.getByLabel('Confirm password').fill(TYPED_PASSWORD)
    await page.getByRole('checkbox', { name: /I have read the privacy notice/ }).check()
    await page.getByRole('button', { name: 'Create my account' }).click()

    await expect(page.getByRole('heading', { name: 'Check your email' })).toBeFocused()
    await expect(page.getByText('The link cannot reach this address')).toBeVisible()
    await expectClean(page, 'SC-05 with the link that cannot reach the address')
  })

  test('an address confirmed from its link has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(
      page,
      { ...customerScreen('SC-05'), path: '/register#verify=a-verification-token', heading: 'Confirm your email address', loaded: 'Your email address is confirmed' },
      { 'POST /api/auth/email-verification': new Answered(204, null) },
    )

    await expectClean(page, 'SC-05 with the address confirmed')
  })
})

test('a booking reviewed, held and confirmed, whose email will not arrive, has no serious or critical accessibility violations', async ({
  page,
}) => {
  await openCustomerScreen(page, customerScreen('SC-04'))
  await expectClean(page, 'SC-04 with the basket to review')

  await page.getByRole('button', { name: 'Review and book' }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Step 1 of 3. Review the cost' })).toBeFocused()
  await expectClean(page, 'SC-04 with the cost to review')

  await page.getByRole('button', { name: 'Hold this equipment' }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Step 2 of 3. Hold the equipment' })).toBeFocused()
  await expectClean(page, 'SC-04 with the equipment held')

  await page.getByRole('button', { name: 'Confirm this hire' }).click()
  await expect(page.getByRole('heading', { level: 2, name: 'Step 3 of 3. Your hire is confirmed' })).toBeFocused()
  await expect(
    page.getByText(/This demonstration delivers email to one address only, so the confirmation email will not arrive\./),
  ).toBeVisible()
  await expect(page.getByText(/A confirmation email is on its way/)).toHaveCount(0)
  await expectClean(page, 'SC-04 with the hire confirmed')
})

test.describe('empty and failed states', () => {
  test('the catalogue with the API down has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, { ...customerScreen('SC-01'), loaded: /^We could not load/ }, {
      'GET /api/catalogue/models': API_DOWN,
      'GET /api/catalogue/categories': API_DOWN,
    })
    await expectClean(page, 'SC-01 with the API down')
  })

  test('a search with nothing free has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, { ...customerScreen('SC-02'), loaded: 'Nothing matches that search' }, {
      'GET /api/catalogue/availability': availabilityOf([]),
    })
    await expectClean(page, 'SC-02 with nothing free')
  })

  test('My Hires with no bookings has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, { ...customerScreen('SC-07'), loaded: 'You have no bookings yet' }, {
      'GET /api/reservations': emptyPage(20),
    })
    await expectClean(page, 'SC-07 with no bookings')
  })

  test('a booking that cannot be found has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(
      page,
      { ...customerScreen('SC-08'), heading: 'We cannot find that booking', loaded: 'No booking with that reference' },
      { [`GET /api/reservations/${BOOKING_REFERENCE}`]: problem(404, 'not-found', 'No reservation has that reference.') },
    )
    await expectClean(page, 'SC-08 not found')
  })

  test('My Account with no hires has no serious or critical accessibility violations', async ({ page }) => {
    await openCustomerScreen(page, { ...customerScreen('SC-09'), loaded: 'No hires yet' }, {
      'GET /api/me/rentals': emptyPage(5),
    })
    await expectClean(page, 'SC-09 with no hires')
  })

  test('a new booking with no customer chosen has no serious or critical accessibility violations', async ({ page }) => {
    await openCounterScreen(page, { id: 'SC-13', path: '/counter/booking', heading: 'New booking', loaded: 'Find the customer first' })
    await expectClean(page, 'SC-13 with no customer chosen')
  })

  test('the overdue worklist with nothing overdue has no serious or critical accessibility violations', async ({ page }) => {
    await openCounterScreen(
      page,
      { id: 'SC-18', path: '/counter/overdue', heading: 'Overdue and late fees', loaded: /^Nothing is overdue at / },
      { 'GET /api/rentals': emptyPage(20) },
    )
    await expectClean(page, 'SC-18 with nothing overdue')
  })

  test('the audit trail with nothing recorded has no serious or critical accessibility violations', async ({ page }) => {
    const trail = ADMIN_SCREENS.find((screen) => screen.path === '/admin/audit')
    if (trail === undefined) throw new Error('ADMIN_SCREENS has no audit trail to open.')
    await openAdminScreen(page, { ...trail, loaded: 'Nothing was recorded that matches' }, {
      'GET /api/admin/audit-events': emptyPage(20),
    })
    await expectClean(page, 'SC-24 with nothing recorded')
  })

  test('the report with the API down has no serious or critical accessibility violations', async ({ page }) => {
    const report = ADMIN_SCREENS.find((screen) => screen.path === '/admin/reports')
    if (report === undefined) throw new Error('ADMIN_SCREENS has no report to open.')
    await openAdminScreen(page, { ...report, loaded: /^We could not load/ }, {
      'GET /api/admin/reports/utilisation': API_DOWN,
    })
    await expectClean(page, 'SC-22 with the API down')
  })
})
