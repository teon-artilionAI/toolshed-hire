/**
 * Customers, counter bookings, checkouts and hires for tests, shaped the way
 * the contract for the counter describes them.
 *
 * The counter assistant in these tests is `COUNTER_STAFF` from
 * session-samples.ts, who works at Bellville, so the bookings here are
 * collected at Bellville. The clock of the tests that use them is pinned to
 * `TEST_NOW`, so today is `TEST_TODAY`.
 *
 * As with the reservation samples, the figures do not add up on purpose. A
 * screen that worked one out for itself could not arrive at them.
 */

import type {
  CustomerPage,
  CustomerSummary,
  Rental,
  Reservation,
  ReservationCheckout,
} from '../shared/api/contract'
import { createdResponse, jsonResponse } from './api-mock'
import type { RouteTable } from './api-mock'
import { PLATE_COMPACTOR, TEST_TODAY, TRENCH_RAMMER, branchAnswers } from './catalogue-samples'
import { DRAFT, REFERENCE, RESERVATION_ID } from './reservation-samples'

export const CUSTOMER_ID = '7a1d0c4e-0000-4000-8000-000000000301'
export const SECOND_CUSTOMER_ID = '7a1d0c4e-0000-4000-8000-000000000302'
export const ON_HOLD_CUSTOMER_ID = '7a1d0c4e-0000-4000-8000-000000000303'
export const RENTAL_ID = '9c3b1f2a-0000-4000-8000-000000000099'
export const RENTAL_REFERENCE = 'TSH-H-26-000099'
export const DAY_AFTER_TODAY = '2026-03-13'

export const CUSTOMERS_ROUTE = 'GET /api/customers'
export const REGISTER_WALK_IN_ROUTE = 'POST /api/customers'
export const AVAILABILITY_ROUTE = 'GET /api/catalogue/availability'

export function customerRoute(id: string = CUSTOMER_ID): string {
  return `GET /api/customers/${id}`
}

export function modelAvailabilityRoute(slug: string = PLATE_COMPACTOR.slug): string {
  return `GET /api/catalogue/models/${slug}/availability`
}

export function checkoutRoute(idOrReference: string = REFERENCE): string {
  return `GET /api/reservations/${idOrReference}/checkout`
}

export function handoverRoute(idOrReference: string = REFERENCE): string {
  return `POST /api/reservations/${idOrReference}/checkout`
}

/** A walk in, registered at the counter, with no login. */
export const THANDI: CustomerSummary = {
  id: CUSTOMER_ID,
  displayName: 'Thandi Mokoena',
  email: null,
  phone: '0824417719',
  hasLogin: false,
  emailVerified: false,
  customerType: 'INDIVIDUAL',
  companyName: null,
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  accountStatus: 'ACTIVE',
  tradeDiscountPercent: '0.00',
  noShowCount: 0,
  homeBranchCode: 'BLV',
}

/** A trade customer who signs in online. */
export const WESLEY: CustomerSummary = {
  ...THANDI,
  id: SECOND_CUSTOMER_ID,
  displayName: 'Wesley Adonis',
  email: 'w.adonis@buildright.co.za',
  phone: '0824417720',
  hasLogin: true,
  emailVerified: true,
  customerType: 'TRADE',
  companyName: 'BuildRight Construction',
  tradeDiscountPercent: '10.00',
  homeBranchCode: 'CBD',
}

/** A customer whose account is on hold. */
export const ON_HOLD: CustomerSummary = {
  ...THANDI,
  id: ON_HOLD_CUSTOMER_ID,
  displayName: 'Sipho Ndlovu',
  phone: '0731112233',
  accountStatus: 'ON_HOLD',
  noShowCount: 3,
}

/** One page of customers, the way `GET /api/customers` answers. */
export function customerPage(items: CustomerSummary[], overrides: Partial<CustomerPage> = {}): CustomerPage {
  return { items, page: 1, pageSize: 10, total: items.length, ...overrides }
}

/** A booking made at the counter for Thandi, collected at Bellville today. */
export const COUNTER_DRAFT: Reservation = {
  ...DRAFT,
  branchCode: 'BLV',
  branchName: 'Bellville',
  from: TEST_TODAY,
  to: DAY_AFTER_TODAY,
  hireDays: 1,
  customerName: THANDI.displayName,
}

export const COUNTER_HELD: Reservation = {
  ...COUNTER_DRAFT,
  status: 'HELD',
  lines: COUNTER_DRAFT.lines.map((line) => ({
    ...line,
    allocatedCount: line.quantity,
    assetTags: ['TSH-PC-0007', 'TSH-PC-0011'],
  })),
  holdExpiresAt: '2026-03-12T08:30:00+02:00',
  canHold: false,
  canConfirm: true,
}

export const COUNTER_CONFIRMED: Reservation = {
  ...COUNTER_HELD,
  status: 'CONFIRMED',
  holdExpiresAt: null,
  confirmedAt: '2026-03-12T08:05:00+02:00',
  canConfirm: false,
}

/** What the counter reads to hand the confirmed booking over. One unit has an
 *  hour meter and one does not. */
export const READY_CHECKOUT: ReservationCheckout = {
  reservationId: RESERVATION_ID,
  reference: REFERENCE,
  status: 'CONFIRMED',
  branchCode: 'BLV',
  branchName: 'Bellville',
  customer: {
    id: CUSTOMER_ID,
    displayName: THANDI.displayName,
    phone: THANDI.phone,
    idDocumentType: 'SA_ID',
    idDocumentLast4: '5083',
    accountStatus: 'ACTIVE',
  },
  from: TEST_TODAY,
  to: DAY_AFTER_TODAY,
  hireDays: 1,
  units: [
    {
      allocationId: 'a1100000-0000-4000-8000-000000000001',
      assetTag: 'TSH-PC-0007',
      modelName: 'CP 100 Plate Compactor',
      modelSlug: PLATE_COMPACTOR.slug,
      conditionGrade: 'B',
      hourMeter: 1250,
      depositPerUnit: '1500.00',
    },
    {
      allocationId: 'a1100000-0000-4000-8000-000000000002',
      assetTag: 'TSH-PC-0011',
      modelName: 'CP 100 Plate Compactor',
      modelSlug: PLATE_COMPACTOR.slug,
      conditionGrade: 'A',
      hourMeter: null,
      depositPerUnit: '1500.00',
    },
  ],
  hireTotalIncVat: '4444.44',
  depositTotal: '5555.55',
  canCheckOut: true,
  refusal: null,
  rentalId: null,
  unitsShort: 0,
}

/** The replacement value copied onto the booking of each unit, which no model
 *  price list would give. */
export const REPLACEMENT_VALUES = ['9876.54', '8765.43']

/** The hire the handover makes. */
export const RENTAL: Rental = {
  id: RENTAL_ID,
  reference: RENTAL_REFERENCE,
  status: 'OPEN',
  reservationId: RESERVATION_ID,
  reservationReference: REFERENCE,
  branchCode: 'BLV',
  branchName: 'Bellville',
  customerProfileId: CUSTOMER_ID,
  customerName: THANDI.displayName,
  customerPhone: THANDI.phone,
  from: TEST_TODAY,
  dueBackOn: DAY_AFTER_TODAY,
  checkedOutAt: '2026-03-12T08:10:00+02:00',
  returnedAt: null,
  items: READY_CHECKOUT.units.map((unit, index) => ({
    id: `b2200000-0000-4000-8000-00000000000${index + 1}`,
    assetTag: unit.assetTag,
    modelName: unit.modelName,
    modelSlug: unit.modelSlug,
    conditionOut: unit.conditionGrade,
    conditionIn: null,
    hourMeterOut: unit.hourMeter,
    hourMeterIn: null,
    accessoriesOut: null,
    accessoriesIn: null,
    returnedAt: null,
    daysLate: 0,
    lateFeePerDay: '220.00',
    daysLateToday: 0,
    lateFeeToday: '0.00',
    damageAssessment: 'NOT_NEEDED',
    replacementValue: REPLACEMENT_VALUES[index],
  })),
  charges: [
    {
      id: 'c3300000-0000-4000-8000-000000000001',
      type: 'DEPOSIT_HOLD',
      description: 'Deposit held at collection',
      amountExVat: '5555.55',
      vatRate: '0.00',
      vatAmount: '0.00',
      amountIncVat: '5555.55',
      status: 'SETTLED',
      raisedAt: '2026-03-12T08:10:00+02:00',
      rentalItemId: null,
      reversesChargeId: null,
      reason: null,
    },
  ],
  depositHeld: '5555.55',
  depositWithheld: '0.00',
  depositRefunded: '0.00',
  balanceDue: '0.00',
  settledAt: null,
  agreementSigned: true,
  canReturn: true,
  // Both units are out, so the deposit waits on them, as the server says of
  // every hire that has just opened.
  settlementWaitingOn: 'ITEMS_OUT',
}

/** What the tool finder lists at Bellville. Both models are free there. */
export const FREE_AT_BELLVILLE = {
  from: TEST_TODAY,
  to: DAY_AFTER_TODAY,
  hireDays: 1,
  items: [
    { model: PLATE_COMPACTOR, branches: branchAnswers(true, true, false) },
    { model: TRENCH_RAMMER, branches: branchAnswers(false, true, false) },
  ],
  page: 1,
  pageSize: 6,
  total: 2,
}

/** The answer for one model at Bellville, free or not. */
export function modelAvailabilityAtBellville(free: boolean, quantity = 1) {
  return {
    from: TEST_TODAY,
    to: DAY_AFTER_TODAY,
    hireDays: 1,
    quantity,
    branches: branchAnswers(true, free, false),
  }
}

/** A counter booking in which every request works. */
export const COUNTER_BOOKING_WORKS: RouteTable = {
  [customerRoute()]: () => jsonResponse(THANDI),
  [AVAILABILITY_ROUTE]: () => jsonResponse(FREE_AT_BELLVILLE),
  [modelAvailabilityRoute()]: (request) =>
    jsonResponse(modelAvailabilityAtBellville(true, Number(request.query.get('quantity') ?? '1'))),
  'POST /api/reservations': () => createdResponse(COUNTER_DRAFT),
  [`POST /api/reservations/${RESERVATION_ID}/hold`]: () => jsonResponse(COUNTER_HELD),
  [`POST /api/reservations/${RESERVATION_ID}/confirm`]: () => jsonResponse(COUNTER_CONFIRMED),
  [`POST /api/reservations/${RESERVATION_ID}/cancellation`]: () =>
    jsonResponse({ ...COUNTER_HELD, status: 'CANCELLED', canCancel: false }),
}
