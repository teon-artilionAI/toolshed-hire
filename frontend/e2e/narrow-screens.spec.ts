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
 * The owner's dashboard and report, by model and by unit, the audit trail and
 * the notification log, and the catalogue with its form closed and open, are
 * checked too, with the answers in admin-answers.ts. The catalogue is checked
 * again with every question it asks open. The asset register is checked
 * with no unit open and with one open, and again with the unit's question,
 * its paperwork form and the registration form open. The staff accounts and
 * the customer holds are checked loaded, and again with their forms and
 * questions open in user-management.spec.ts, which measures with the same
 * rule from overflow.ts. So are the return screen and the checkout as the
 * owner sees them, each with the owner's question open, from owner-answers.ts.
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
import { ADMIN_SCREENS, ASSET_REGISTER_HEADING, CATALOGUE_HEADING, openAdminScreen } from './admin-answers.ts'
import { COUNTER_SCREENS, openCounterScreen } from './counter-answers.ts'
import { NARROW_PHONE, ROUNDING_PIXELS, SIDEWAYS_OVERFLOW } from './overflow.ts'
import { OWNER_COUNTER_SCREENS } from './owner-answers.ts'
import { MY_RENTALS } from './return-answers.ts'

/** What the session leaves in web storage once somebody has signed in. Without
 *  it the application does not ask whether there is a session. */
const SESSION_HINT = "window.localStorage.setItem('toolshed.session-hint', 'yes')"

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

for (const adminScreen of ADMIN_SCREENS) {
  test(`${adminScreen.path} fits 360 pixels with long names and large figures, with nothing to scroll sideways`, async ({
    page,
  }) => {
    await openAdminScreen(page, adminScreen)

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
}

test('the catalogue fits 360 pixels with its questions and the category form open, with nothing to scroll sideways', async ({
  page,
}) => {
  const formOpen = ADMIN_SCREENS.find((screen) => screen.heading === CATALOGUE_HEADING && screen.path.includes('model='))
  if (formOpen === undefined) throw new Error('ADMIN_SCREENS has no catalogue with its form open.')
  await openAdminScreen(page, formOpen)

  const form = page.getByRole('form', { name: /^The details of / })
  await form.getByLabel('Daily rate, in rand').fill('1300')
  await form.getByRole('button', { name: 'Save the changes' }).click()
  await expect(page.getByRole('heading', { level: 3, name: /^Save the changes to .+\?$/ })).toBeVisible()
  await page.getByRole('button', { name: /^Hide / }).first().click()
  await expect(page.getByRole('heading', { level: 3, name: /^Hide .+ from customers\?$/ })).toBeVisible()
  await page.getByRole('region', { name: 'Categories' }).getByRole('button', { name: 'Add a category' }).click()
  await page.getByRole('button', { name: /^Switch off / }).first().click()
  await expect(page.getByRole('heading', { level: 3, name: /^Switch .+ off\?$/ })).toBeVisible()

  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
})

test('the asset register fits 360 pixels with a unit, its question, its form and the registration open, with nothing to scroll sideways', async ({
  page,
}) => {
  const unitOpen = ADMIN_SCREENS.find((screen) => screen.heading === ASSET_REGISTER_HEADING && screen.path.includes('asset='))
  if (unitOpen === undefined) throw new Error('ADMIN_SCREENS has no asset register with a unit open.')
  await openAdminScreen(page, unitOpen)

  await page.getByRole('region', { name: 'Move it through its life' }).getByRole('button', { name: 'Retire it' }).click()
  await expect(page.getByRole('heading', { level: 4, name: /^Retire .+\?$/ })).toBeVisible()
  await page.getByRole('button', { name: 'Change the serial number, grade, meter reading or notes' }).click()
  await expect(page.getByRole('form', { name: /^The details of / })).toBeVisible()
  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

  await page.getByRole('button', { name: 'Register a unit' }).first().click()
  const form = page.getByRole('form', { name: 'The new unit' })
  await form.getByRole('button', { name: 'Register the unit' }).click()
  await expect(page.getByText(/Nothing has been saved yet\. 3 answers need fixing\./)).toBeVisible()
  expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
})

for (const owner of OWNER_COUNTER_SCREENS) {
  test(`${owner.name} fits 360 pixels, question and all, with nothing to scroll sideways`, async ({ page }) => {
    await openCounterScreen(page, owner.screen, owner.instead)
    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)

    await owner.ask(page)
    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
}

for (const counterScreen of COUNTER_SCREENS) {
  test(`${counterScreen.heading} fits 360 pixels with long names, with nothing to scroll sideways`, async ({
    page,
  }) => {
    await openCounterScreen(page, counterScreen)

    expect(await page.evaluate<number>(SIDEWAYS_OVERFLOW)).toBeLessThanOrEqual(ROUNDING_PIXELS)
  })
}
