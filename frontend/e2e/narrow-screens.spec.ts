/**
 * My Hires, My Account and the counter's booking screens on a phone 360
 * pixels wide.
 *
 * Both customer screens used to need scrolling sideways at this width. The
 * list of bookings was a table of six columns inside a box that scrolled, with
 * the status and the total out of sight, and the account screen pushed the
 * whole page wider than the window. Only a real browser can measure that, so
 * the check is here and not among the component tests. The counter's customer
 * lookup, new booking, checkout, dashboard, diary, locator, return screen,
 * overdue worklist and damage screen are checked the same way, because an
 * assistant may hold a phone at the counter. My Account is checked with a hire in its history.
 *
 * This spec does not use the real backend. The screens need a signed in person
 * with bookings and a profile, and a layout check should not depend on what a
 * database happens to hold. So the spec answers the API itself, with bodies
 * shaped the way the contract describes them and with long names and
 * addresses, which are what break a layout. The counter's answers are in
 * counter-answers.ts, which the accessibility spec shares. It runs with or
 * without a backend.
 *
 * It sets its own viewport, so both browser projects check the same width.
 */

import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
import { MY_RENTALS } from './return-answers.ts'

/** The narrowest phone the screens are built for. */
const NARROW_PHONE = { width: 360, height: 780 }

/** What the session leaves in web storage once somebody has signed in. Without
 *  it the application does not ask whether there is a session. */
const SESSION_HINT = "window.localStorage.setItem('toolshed.session-hint', 'yes')"

/**
 * How far anything runs past its box sideways, in pixels. The page itself,
 * and every box inside the screen that is allowed to scroll sideways. Written
 * as text because the browser runs it, and this file is compiled without the
 * browser types.
 */
const SIDEWAYS_OVERFLOW = `Math.max(
  document.documentElement.scrollWidth - document.documentElement.clientWidth,
  ...Array.from(document.querySelectorAll('main *'), (element) =>
    ['auto', 'scroll'].includes(getComputedStyle(element).overflowX)
      ? element.scrollWidth - element.clientWidth
      : 0,
  ),
)`

/** A pixel of rounding is not a scroll bar. */
const ROUNDING_PIXELS = 1

const CUSTOMER = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000001',
  email: 'wesley.bartholomew.adonis@buildright-construction.co.za',
  fullName: 'Wesley Bartholomew Adonis-Vanderheyden',
  role: 'customer',
  branchCode: null,
  emailVerified: false,
}

const SESSION = { accessToken: 'narrow-screen-token', tokenType: 'Bearer', expiresIn: 900, user: CUSTOMER }

const BRANCHES = {
  items: [
    { code: 'SMW', name: 'Somerset West', suburb: 'Firgrove', city: 'Cape Town', phone: '021 555 0163', opensAt: '07:00', closesAt: '17:00' },
  ],
}

function reservation(number: number, status: string, holdExpiresAt: string | null) {
  return {
    id: `5f0c2a9e-0000-4000-8000-00000000012${number}`,
    reference: `TSH-R-26-00012${number}`,
    status,
    branchCode: 'SMW',
    branchName: 'Somerset West',
    from: '2026-10-12',
    to: '2026-10-16',
    hireDays: 4,
    lines: [
      { modelSlug: 'cp-100-plate-compactor', modelName: 'CP 100 Plate Compactor', quantity: 2, dailyRate: '340.00', weeklyRate: '1360.00', depositPerUnit: '1500.00', lineSubtotalExVat: '2720.00', allocatedCount: 2, assetTags: [] },
      { modelSlug: 'te-1000-avr-breaker', modelName: 'TE 1000-AVR Demolition Breaker', quantity: 1, dailyRate: '620.00', weeklyRate: '2480.00', depositPerUnit: '2500.00', lineSubtotalExVat: '2480.00', allocatedCount: 1, assetTags: [] },
    ],
    subtotalExVat: '5200.00',
    discountPercent: '0.00',
    vatAmount: '780.00',
    estimatedTotalIncVat: '115980.00',
    depositTotal: '5500.00',
    holdExpiresAt,
    confirmedAt: null,
    cancelledAt: null,
    cancellationReason: null,
    canHold: false,
    canConfirm: false,
    canCancel: true,
    customerName: CUSTOMER.fullName,
    createdAt: '2026-10-03T08:00:00+02:00',
  }
}

const RESERVATIONS = {
  items: [
    reservation(4, 'CONFIRMED', null),
    reservation(5, 'HELD', '2026-10-03T08:30:00+02:00'),
    reservation(6, 'NO_SHOW', null),
  ],
  page: 1,
  pageSize: 20,
  total: 45,
}

const PROFILE = {
  fullName: CUSTOMER.fullName,
  email: CUSTOMER.email,
  emailVerified: false,
  phone: '0824417719',
  customerType: 'TRADE',
  companyName: 'BuildRight Construction and Civils (Pty) Ltd',
  vatNumber: '4123456789',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingAddressLine1: '12 Loop Street, Unit 4, Montague Gardens Industrial Park',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
  accountStatus: 'ON_HOLD',
  tradeDiscountPercent: '10.00',
  noShowCount: 3,
  homeBranchCode: 'SMW',
  memberSince: '2026-10-03',
}

/** What each route answers. Anything else is a 404, as from a backend without it. */
const ANSWERS: Record<string, unknown> = {
  'POST /api/auth/refresh': SESSION,
  'GET /api/branches': BRANCHES,
  'GET /api/reservations': RESERVATIONS,
  'GET /api/me/profile': PROFILE,
  'GET /api/me/rentals': MY_RENTALS,
}

/** What the list answers when it is only asked how many bookings were left
 *  unfinished. None were. */
const NO_UNFINISHED = { items: [], page: 1, pageSize: 1, total: 0 }

async function answerTheApi(route: Route): Promise<void> {
  const request = route.request()
  const address = new URL(request.url())
  const key = `${request.method()} ${address.pathname}`
  const body = address.searchParams.get('status') === 'DRAFT' ? NO_UNFINISHED : ANSWERS[key]
  if (body === undefined) {
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    return
  }
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
}

async function openAsCustomer(page: Page, path: string, heading: string): Promise<void> {
  await page.addInitScript(SESSION_HINT)
  await page.route('**/api/**', answerTheApi)
  await page.goto(path)
  await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
}

test.use({ viewport: NARROW_PHONE })

test('My Hires shows every booking in full at 360 pixels, with nothing to scroll sideways', async ({ page }) => {
  await openAsCustomer(page, '/reservations', 'My hires')

  // Every value of the first booking is on the screen, with its name beside it.
  const first = page.getByRole('row').filter({ hasText: 'TSH-R-26-000124' })
  await first.scrollIntoViewIfNeeded()
  await expect(first.getByText('Hire dates')).toBeVisible()
  await expect(first.getByText('Confirmed')).toBeInViewport()
  await expect(first.getByText(/R\s115\s980[,.]00/)).toBeInViewport()
  await expect(first.getByRole('link', { name: 'View booking TSH-R-26-000124' })).toBeVisible()
  await expect(page.getByRole('row')).toHaveCount(RESERVATIONS.items.length)

  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
})

test('My Account fits 360 pixels with long details, reading and editing', async ({ page }) => {
  await openAsCustomer(page, '/account', 'My account')
  await expect(page.getByText('Your email address has not been confirmed')).toBeVisible()
  await expect(page.getByText(PROFILE.companyName)).toBeVisible()
  await expect(page.getByRole('article', { name: 'TSH-H-26-000099' })).toBeVisible()

  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

  await page.getByRole('button', { name: 'Edit my details' }).click()
  await expect(page.getByLabel('Billing address, first line')).toHaveValue(PROFILE.billingAddressLine1)

  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
})

for (const counterScreen of COUNTER_SCREENS) {
  test(`${counterScreen.heading} fits 360 pixels with long names, with nothing to scroll sideways`, async ({
    page,
  }) => {
    await openCounterScreen(page, counterScreen)

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
}
