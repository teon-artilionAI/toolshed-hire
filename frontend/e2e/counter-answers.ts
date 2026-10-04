/**
 * The API answered by the spec itself, for the counter screens.
 *
 * The accessibility scan and the narrow screen check of SC-12, SC-13 and SC-14
 * need a signed in counter assistant, a customer, a booking and a checkout. A
 * scan should not depend on what a database happens to hold, and it should
 * run with or without a backend, so these answers stand in for the API. They
 * are shaped the way the contract for the counter describes them, with long
 * names, which are what break a layout. The dashboard, the diary and the
 * locator, SC-10, SC-11 and SC-17, are scanned the same way, and their answers
 * are in overview-answers.ts. So are the return screen and the overdue
 * worklist, SC-15 and SC-18, whose answers are in return-answers.ts, and the
 * damage screen, SC-16, whose answers are in damage-answers.ts.
 */

import { expect } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { fulfil } from './answered.ts'
import { DAMAGE_ANSWERS, DAMAGE_PATH } from './damage-answers.ts'
import { dateFromToday } from './hire-dates.ts'
import { OVERVIEW_ANSWERS } from './overview-answers.ts'
import { RETURN_ANSWERS, RETURN_RENTAL_ID } from './return-answers.ts'

/** What the session leaves in web storage once somebody has signed in. Without
 *  it the application does not ask whether there is a session. */
const SESSION_HINT = "window.localStorage.setItem('toolshed.session-hint', 'yes')"

const CUSTOMER_ID = '7a1d0c4e-0000-4000-8000-000000000301'
const RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000124'
const REFERENCE = 'TSH-R-26-000124'
const MODEL_SLUG = 'cp-100-plate-compactor'

const TODAY = dateFromToday(0)
const TOMORROW = dateFromToday(1)

const ASSISTANT = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000003',
  email: 'elmarie@toolshedhire.co.za',
  fullName: 'Elmarie Fourie-Vanderwesthuizen',
  role: 'counter',
  branchCode: 'CBD',
  emailVerified: true,
  emailDeliverable: true,
}

const BRANCHES = {
  items: [
    { code: 'CBD', name: 'Cape Town CBD', suburb: 'Woodstock', city: 'Cape Town', phone: '021 555 0142', opensAt: '07:00', closesAt: '17:00' },
    { code: 'BLV', name: 'Bellville', suburb: 'Stikland', city: 'Cape Town', phone: '021 555 0157', opensAt: '07:00', closesAt: '17:00' },
  ],
}

const CUSTOMER = {
  id: CUSTOMER_ID,
  displayName: 'Thandiwe Nomvula Mokoena-Hendricks',
  email: null,
  phone: '0824417719',
  hasLogin: false,
  emailVerified: false,
  customerType: 'TRADE',
  companyName: 'BuildRight Construction and Civils (Pty) Ltd',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingSuburb: 'Montague Gardens Industrial Park',
  billingCity: 'Cape Town',
  accountStatus: 'ACTIVE',
  tradeDiscountPercent: '10.00',
  noShowCount: 1,
  homeBranchCode: 'CBD',
}

const MODEL = {
  sku: 'PC-WACKER-CP100',
  slug: MODEL_SLUG,
  name: 'CP 100 Plate Compactor with Water Tank',
  manufacturer: 'Wacker Neuson',
  modelNumber: 'CP 100',
  categoryCode: 'COMPACTION',
  categoryName: 'Compaction',
  shortDescription: 'Forward plate compactor.',
  dailyRate: '340.00',
  weeklyRate: '1360.00',
  depositAmount: '1500.00',
  minHireDays: 1,
  maxHireDays: 28,
  imagePath: null,
}

const ANSWERS_FROM = [
  { branchCode: 'CBD', branchName: 'Cape Town CBD', available: true },
  { branchCode: 'BLV', branchName: 'Bellville', available: false },
]

const RESERVATION = {
  id: RESERVATION_ID,
  reference: REFERENCE,
  status: 'CONFIRMED',
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  from: TODAY,
  to: TOMORROW,
  hireDays: 1,
  lines: [
    { modelSlug: MODEL_SLUG, modelName: MODEL.name, quantity: 2, dailyRate: '340.00', weeklyRate: '1360.00', depositPerUnit: '1500.00', lineSubtotalExVat: '680.00', allocatedCount: 2, assetTags: ['TSH-PC-0007', 'TSH-PC-0011'] },
  ],
  subtotalExVat: '612.00',
  discountPercent: '10.00',
  vatAmount: '91.80',
  estimatedTotalIncVat: '703.80',
  depositTotal: '3000.00',
  holdExpiresAt: null,
  confirmedAt: `${TODAY}T08:05:00+02:00`,
  cancelledAt: null,
  cancellationReason: null,
  canHold: false,
  canConfirm: false,
  canCancel: true,
  customerName: CUSTOMER.displayName,
  createdAt: `${TODAY}T08:00:00+02:00`,
}

/** What the checkout of the booking answers, by its route. owner-answers.ts
 *  answers the same route with the booking short of a unit. */
export const CHECKOUT_ROUTE = `GET /api/reservations/${REFERENCE}/checkout`

export const CHECKOUT = {
  reservationId: RESERVATION_ID,
  reference: REFERENCE,
  status: 'CONFIRMED',
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  customer: { id: CUSTOMER_ID, displayName: CUSTOMER.displayName, phone: CUSTOMER.phone, idDocumentType: 'SA_ID', idDocumentLast4: '5083', accountStatus: 'ACTIVE' },
  from: TODAY,
  to: TOMORROW,
  hireDays: 1,
  units: [
    { allocationId: 'a1100000-0000-4000-8000-000000000001', assetTag: 'TSH-PC-0007', modelName: MODEL.name, modelSlug: MODEL_SLUG, conditionGrade: 'B', hourMeter: 1250, depositPerUnit: '1500.00' },
    { allocationId: 'a1100000-0000-4000-8000-000000000002', assetTag: 'TSH-PC-0011', modelName: MODEL.name, modelSlug: MODEL_SLUG, conditionGrade: 'A', hourMeter: null, depositPerUnit: '1500.00' },
  ],
  hireTotalIncVat: '703.80',
  depositTotal: '3000.00',
  canCheckOut: true,
  refusal: null,
  rentalId: null,
  unitsShort: 0,
}

/** What each route answers. Anything else is a 404, as from a backend without it. */
const ANSWERS: Record<string, unknown> = {
  'POST /api/auth/refresh': { accessToken: 'counter-scan-token', tokenType: 'Bearer', expiresIn: 900, user: ASSISTANT },
  'GET /api/branches': BRANCHES,
  'GET /api/customers': { items: [CUSTOMER], page: 1, pageSize: 10, total: 1 },
  [`GET /api/customers/${CUSTOMER_ID}`]: CUSTOMER,
  'GET /api/reservations': { items: [RESERVATION], page: 1, pageSize: 10, total: 1 },
  'GET /api/catalogue/availability': {
    from: TODAY,
    to: TOMORROW,
    hireDays: 1,
    items: [{ model: MODEL, branches: ANSWERS_FROM }],
    page: 1,
    pageSize: 6,
    total: 1,
  },
  [`GET /api/catalogue/models/${MODEL_SLUG}/availability`]: { from: TODAY, to: TOMORROW, hireDays: 1, quantity: 1, branches: ANSWERS_FROM },
  [CHECKOUT_ROUTE]: CHECKOUT,
  ...OVERVIEW_ANSWERS,
  ...RETURN_ANSWERS,
  ...DAMAGE_ANSWERS,
}

/** Answer the API from `ANSWERS`, with the answers a scan names in place of
 *  the ones they share a route with. */
function answerTheApi(instead: Record<string, unknown>): (route: Route) => Promise<void> {
  return async (route) => {
    const request = route.request()
    const key = `${request.method()} ${new URL(request.url()).pathname}`
    await fulfil(route, instead[key] ?? ANSWERS[key])
  }
}

/** A counter screen to open, and the heading that proves it has loaded. */
export interface CounterScreen {
  /** The identifier in navigation.ts. */
  id: string
  path: string
  heading: string
  /** Something that is only on the page once the screen has its data. */
  loaded: string | RegExp
}

export const COUNTER_SCREENS: readonly CounterScreen[] = [
  { id: 'SC-12', path: `/counter/customers?q=thandi&customer=${CUSTOMER_ID}`, heading: 'Find a customer', loaded: 'Their bookings' },
  { id: 'SC-13', path: `/counter/booking?customer=${CUSTOMER_ID}`, heading: 'New booking', loaded: /1 model is free at Cape Town CBD/ },
  { id: 'SC-14', path: `/counter/checkout/${REFERENCE}`, heading: 'Checkout and deposit', loaded: 'Deposit to take now' },
  { id: 'SC-10', path: '/counter', heading: 'Today at the counter', loaded: 'Late fee so far' },
  { id: 'SC-11', path: '/counter/diary', heading: 'Branch diary', loaded: 'Booked, not collected yet' },
  { id: 'SC-17', path: '/counter/locator?q=TSH', heading: 'Where is it', loaded: 'Quarantined until inspected' },
  { id: 'SC-15', path: `/counter/return/${RETURN_RENTAL_ID}`, heading: 'Return and condition inspection', loaded: 'Units still out' },
  { id: 'SC-18', path: '/counter/overdue', heading: 'Overdue and late fees', loaded: 'Escalation queue, more than 14 days late' },
  { id: 'SC-16', path: DAMAGE_PATH, heading: 'Record damage', loaded: 'TSH-D-26-00012' },
]

/**
 * Open a counter screen as a signed in assistant, with the API answered here.
 *
 * @param instead Answers that take the place of the shared ones for this
 *   screen, by method and path, such as the owner's session.
 */
export async function openCounterScreen(
  page: Page,
  screen: CounterScreen,
  instead: Record<string, unknown> = {},
): Promise<void> {
  await page.addInitScript(SESSION_HINT)
  await page.route('**/api/**', answerTheApi(instead))
  await page.goto(screen.path)
  await expect(page.getByRole('heading', { level: 1, name: screen.heading })).toBeVisible()
  await expect(page.getByText(screen.loaded).first()).toBeVisible()
}
