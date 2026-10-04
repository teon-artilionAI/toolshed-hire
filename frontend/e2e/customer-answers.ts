/**
 * The API answered by the spec itself, for the customer's screens.
 *
 * The accessibility scan and the layout check of SC-01 to SC-09 and the
 * privacy notice need a catalogue, a signed in customer with bookings, a
 * profile and a hire, and a booking that can be priced, held and confirmed.
 * A scan should not depend on what a database happens to hold, and it should
 * run with or without a backend, so these answers stand in for the API, with
 * long names and addresses, which are what break a layout. The catalogue
 * answers are in public-answers.ts.
 *
 * The customer's address is one this demonstration cannot deliver email to,
 * so the screens that would promise an email say plainly that it will not
 * arrive, and that is what gets scanned and measured.
 */

import { expect } from '@playwright/test'
import type { Page, Route } from '@playwright/test'
import { Answered, fulfil } from './answered.ts'
import { HIRE_FROM, HIRE_TO, MODEL_NAME, MODEL_SLUG, PUBLIC_ANSWERS } from './public-answers.ts'
import { MY_RENTALS } from './return-answers.ts'

/** What the session leaves in web storage once somebody has signed in. Without
 *  it the application does not ask whether there is a session. */
const SESSION_HINT = "window.localStorage.setItem('toolshed.session-hint', 'yes')"

/** The booking every list and detail answers with. */
export const BOOKING_REFERENCE = 'TSH-R-26-000124'
const BOOKING_ID = '5f0c2a9e-0000-4000-8000-000000000124'

/** How long a hold made here runs, so the countdown is never near its end. */
const HOLD_MINUTES = 25
const MS_PER_MINUTE = 60_000

export const CUSTOMER = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000001',
  email: 'wesley.bartholomew.adonis@buildright-construction.co.za',
  fullName: 'Wesley Bartholomew Adonis-Vanderheyden',
  role: 'customer',
  branchCode: null,
  emailVerified: false,
  emailDeliverable: false,
}

export const PROFILE = {
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

function reservation(number: number, status: string, overrides: Record<string, unknown> = {}) {
  return {
    id: `5f0c2a9e-0000-4000-8000-00000000012${number}`,
    reference: `TSH-R-26-00012${number}`,
    status,
    branchCode: 'SMW',
    branchName: 'Somerset West',
    from: HIRE_FROM,
    to: HIRE_TO,
    hireDays: 4,
    lines: [
      { modelSlug: MODEL_SLUG, modelName: MODEL_NAME, quantity: 2, dailyRate: '340.00', weeklyRate: '1360.00', depositPerUnit: '1500.00', lineSubtotalExVat: '2720.00', allocatedCount: 2, assetTags: [] },
      { modelSlug: 'te-1000-avr-breaker', modelName: 'TE 1000-AVR Demolition Breaker', quantity: 1, dailyRate: '620.00', weeklyRate: '2480.00', depositPerUnit: '2500.00', lineSubtotalExVat: '2480.00', allocatedCount: 1, assetTags: [] },
    ],
    subtotalExVat: '5200.00',
    discountPercent: '0.00',
    vatAmount: '780.00',
    estimatedTotalIncVat: '115980.00',
    depositTotal: '5500.00',
    holdExpiresAt: null,
    confirmedAt: null,
    cancelledAt: null,
    cancellationReason: null,
    canHold: false,
    canConfirm: false,
    canCancel: true,
    customerName: CUSTOMER.fullName,
    createdAt: '2026-10-03T08:00:00+02:00',
    ...overrides,
  }
}

export const RESERVATIONS = {
  items: [
    reservation(4, 'CONFIRMED'),
    reservation(5, 'HELD', { holdExpiresAt: '2026-10-03T08:30:00+02:00' }),
    reservation(6, 'NO_SHOW', { canCancel: false }),
  ],
  page: 1,
  pageSize: 20,
  total: 45,
}

/** What the list answers when it is only asked how many bookings were left
 *  unfinished. None were. */
const NO_UNFINISHED = { items: [], page: 1, pageSize: 1, total: 0 }

/** The booking made from the basket, as it is priced, held and confirmed. */
const DRAFT = reservation(4, 'DRAFT', { id: BOOKING_ID, branchCode: 'CBD', branchName: 'Cape Town CBD', canHold: true })

/** What a request for an email answers. This address cannot be reached. */
const NOT_DELIVERABLE = new Answered(202, { emailDeliverable: false })

/** What each route answers. A body, a body with its own status, or a function
 *  that works one out when it is asked, such as a hold that ends from now. */
const ANSWERS: Record<string, unknown> = {
  ...PUBLIC_ANSWERS,
  'POST /api/auth/refresh': { accessToken: 'customer-scan-token', tokenType: 'Bearer', expiresIn: 900, user: CUSTOMER },
  'POST /api/auth/logout': new Answered(204, null),
  'GET /api/reservations': RESERVATIONS,
  [`GET /api/reservations/${BOOKING_REFERENCE}`]: RESERVATIONS.items[0],
  'GET /api/me/profile': PROFILE,
  'GET /api/me/rentals': MY_RENTALS,
  'POST /api/reservations': new Answered(201, DRAFT),
  [`POST /api/reservations/${BOOKING_ID}/hold`]: () => ({
    ...DRAFT,
    status: 'HELD',
    holdExpiresAt: new Date(Date.now() + HOLD_MINUTES * MS_PER_MINUTE).toISOString(),
    canHold: false,
    canConfirm: true,
  }),
  [`POST /api/reservations/${BOOKING_ID}/confirm`]: { ...DRAFT, status: 'CONFIRMED', confirmedAt: '2026-10-03T08:05:00+02:00', canHold: false },
  'POST /api/auth/register': NOT_DELIVERABLE,
  'POST /api/auth/password-reset/request': NOT_DELIVERABLE,
  'POST /api/auth/email-verification/resend': NOT_DELIVERABLE,
}

/** Answer the API from `ANSWERS`, with the answers a scan names in place of
 *  the ones they share a route with. */
function answerTheApi(instead: Record<string, unknown>): (route: Route) => Promise<void> {
  return async (route) => {
    const request = route.request()
    const address = new URL(request.url())
    const key = `${request.method()} ${address.pathname}`
    const unfinished = key === 'GET /api/reservations' && address.searchParams.get('status') === 'DRAFT'
    await fulfil(route, key in instead ? instead[key] : unfinished ? NO_UNFINISHED : ANSWERS[key])
  }
}

/** The basket the tab holds, in the shape basket-stored-shape.ts writes. */
const STORED_BASKET = JSON.stringify({
  version: 2,
  from: HIRE_FROM,
  to: HIRE_TO,
  branchCode: 'CBD',
  lines: [{ modelSlug: MODEL_SLUG, quantity: 2 }],
  reservationId: null,
  setAside: null,
})

/** A customer screen to open, and what proves it has loaded. */
export interface CustomerScreen {
  /** The identifier in navigation.ts. */
  id: string
  path: string
  heading: string
  /** Something that is only on the page once the screen has its data. */
  loaded: string | RegExp
  /** Opened by the signed in customer, or else by a visitor. */
  signedIn: boolean
  /** With the basket above in the tab. */
  basket?: boolean
}

export const CUSTOMER_SCREENS: readonly CustomerScreen[] = [
  { id: 'SC-01', path: '/', heading: 'Hire tools and plant across Cape Town', loaded: MODEL_NAME, signedIn: false },
  { id: 'SC-02', path: `/search?from=${HIRE_FROM}&to=${HIRE_TO}`, heading: 'What is free for your dates', loaded: MODEL_NAME, signedIn: false },
  { id: 'SC-03', path: `/model/${MODEL_SLUG}?from=${HIRE_FROM}&to=${HIRE_TO}&branch=CBD`, heading: MODEL_NAME, loaded: 'Free at Cape Town CBD', signedIn: false },
  { id: 'SC-04', path: '/basket', heading: 'Your hire basket', loaded: 'Review and book', signedIn: true, basket: true },
  { id: 'SC-05', path: '/register', heading: 'Create your hire account', loaded: 'Full name', signedIn: false },
  { id: 'SC-06', path: '/signin', heading: 'Sign in to Toolshed Hire', loaded: 'Email address', signedIn: false },
  { id: 'SC-07', path: '/reservations', heading: 'My hires', loaded: BOOKING_REFERENCE, signedIn: true },
  { id: 'SC-08', path: `/reservations/${BOOKING_REFERENCE}`, heading: BOOKING_REFERENCE, loaded: 'What you booked', signedIn: true },
  { id: 'SC-09', path: '/account', heading: 'My account', loaded: PROFILE.companyName, signedIn: true },
  { id: 'INFO-01', path: '/privacy', heading: 'Privacy notice', loaded: 'Email is sent through Resend.', signedIn: false },
]

/** A customer screen from the list above, by its identifier. */
export function customerScreen(id: string): CustomerScreen {
  const found = CUSTOMER_SCREENS.find((screen) => screen.id === id)
  if (found === undefined) throw new Error(`CUSTOMER_SCREENS has no screen ${id} to open.`)
  return found
}

/**
 * Open a customer screen with the API answered here.
 *
 * @param instead Answers that take the place of the shared ones for this
 *   visit, by method and path, such as a refusal or an empty list.
 */
export async function openCustomerScreen(
  page: Page,
  screen: CustomerScreen,
  instead: Record<string, unknown> = {},
): Promise<void> {
  if (screen.signedIn) await page.addInitScript(SESSION_HINT)
  if (screen.basket) await page.addInitScript(`window.sessionStorage.setItem('toolshed.basket', ${JSON.stringify(STORED_BASKET)})`)
  await page.route('**/api/**', answerTheApi(instead))
  await page.goto(screen.path)
  await expect(page.getByRole('heading', { level: 1, name: screen.heading })).toBeVisible()
  await expect(page.getByText(screen.loaded).first()).toBeVisible()
}
