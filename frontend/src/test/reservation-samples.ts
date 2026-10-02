/**
 * Sample reservations and reservation routes for tests, shaped the way the
 * contract describes them.
 *
 * The figures on the samples do not add up, on purpose. Two units at 340.00 a
 * day for four days is not 1111.11, and 1111.11 with VAT is not 4444.44. A
 * screen that worked a figure out for itself could not arrive at them, so a
 * test that reads them off the page proves the screen showed what it was sent.
 *
 * The clock of the tests that use these is pinned to `TEST_NOW`, which is
 * 08:00 in Cape Town, so a hold made then runs out at 08:30.
 */

import type { Reservation, ReservationPage } from '../shared/api/contract'
import type { BasketAddition } from '../shared/basket-store'
import { createdResponse, jsonResponse } from './api-mock'
import type { RouteTable } from './api-mock'
import { BRANCHES, PLATE_COMPACTOR_DETAIL, TEST_DEFAULT_RETURN, TEST_TODAY } from './catalogue-samples'

export const RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000124'
export const REFERENCE = 'TSH-R-26-000124'

/** A second reservation, for a hold that is made again. */
export const SECOND_RESERVATION_ID = '5f0c2a9e-0000-4000-8000-000000000125'
export const SECOND_REFERENCE = 'TSH-R-26-000125'

/** Thirty minutes after `TEST_NOW`, and one minute before that. */
export const HOLD_EXPIRES_AT = '2026-03-12T08:30:00+02:00'
export const HOLD_UNTIL_CLOCK = '08:30'

export const COMPACTOR_SLUG = PLATE_COMPACTOR_DETAIL.slug
export const MODEL_ROUTE = `GET /api/catalogue/models/${COMPACTOR_SLUG}`
export const BRANCHES_ROUTE = 'GET /api/branches'

export const LIST_ROUTE = 'GET /api/reservations'
export const CREATE_ROUTE = 'POST /api/reservations'

export function detailRoute(idOrReference: string = RESERVATION_ID): string {
  return `GET /api/reservations/${idOrReference}`
}

export function holdRoute(id: string = RESERVATION_ID): string {
  return `POST /api/reservations/${id}/hold`
}

export function confirmRoute(id: string = RESERVATION_ID): string {
  return `POST /api/reservations/${id}/confirm`
}

export function cancelRoute(id: string = RESERVATION_ID): string {
  return `POST /api/reservations/${id}/cancellation`
}

/** Two plate compactors for the default four days, collected from the CBD. */
export const IN_THE_BASKET: BasketAddition = {
  modelSlug: COMPACTOR_SLUG,
  quantity: 2,
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  branchCode: 'CBD',
}

/** The body the basket above is sent as. */
export const CREATE_REQUEST = {
  branchCode: 'CBD',
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  lines: [{ modelSlug: COMPACTOR_SLUG, quantity: 2 }],
  customerProfileId: null,
  notes: null,
}

export const DRAFT: Reservation = {
  id: RESERVATION_ID,
  reference: REFERENCE,
  status: 'DRAFT',
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  from: TEST_TODAY,
  to: TEST_DEFAULT_RETURN,
  hireDays: 4,
  lines: [
    {
      modelSlug: COMPACTOR_SLUG,
      modelName: 'CP 100 Plate Compactor',
      quantity: 2,
      dailyRate: '340.00',
      weeklyRate: '1360.00',
      depositPerUnit: '1500.00',
      lineSubtotalExVat: '1111.11',
      allocatedCount: 0,
      assetTags: [],
    },
  ],
  subtotalExVat: '1111.11',
  discountPercent: '0.00',
  vatAmount: '333.33',
  estimatedTotalIncVat: '4444.44',
  depositTotal: '5555.55',
  holdExpiresAt: null,
  confirmedAt: null,
  cancelledAt: null,
  cancellationReason: null,
  canHold: true,
  canConfirm: false,
  canCancel: true,
  customerName: 'Wesley Adonis',
  createdAt: '2026-03-12T08:00:00+02:00',
}

export const HELD: Reservation = {
  ...DRAFT,
  status: 'HELD',
  lines: DRAFT.lines.map((line) => ({ ...line, allocatedCount: line.quantity })),
  holdExpiresAt: HOLD_EXPIRES_AT,
  canHold: false,
  canConfirm: true,
}

export const CONFIRMED: Reservation = {
  ...HELD,
  status: 'CONFIRMED',
  holdExpiresAt: null,
  confirmedAt: '2026-03-12T08:05:00+02:00',
  canConfirm: false,
}

export const CANCELLED: Reservation = {
  ...CONFIRMED,
  status: 'CANCELLED',
  cancelledAt: '2026-03-12T09:15:00+02:00',
  cancellationReason: null,
  canCancel: false,
}

export const EXPIRED: Reservation = {
  ...HELD,
  status: 'EXPIRED',
  holdExpiresAt: null,
  canConfirm: false,
  canCancel: false,
}

/** One page of reservations, the way `GET /api/reservations` answers. */
export function pageOf(items: Reservation[], overrides: Partial<ReservationPage> = {}): ReservationPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}

/** What the basket screen reads beside the reservation routes. */
export const BASKET_READS: RouteTable = {
  [MODEL_ROUTE]: () => jsonResponse(PLATE_COMPACTOR_DETAIL),
  [BRANCHES_ROUTE]: () => jsonResponse(BRANCHES),
}

/** A booking in which every request works. */
export const BOOKING_WORKS: RouteTable = {
  ...BASKET_READS,
  [CREATE_ROUTE]: () => createdResponse(DRAFT),
  [holdRoute()]: () => jsonResponse(HELD),
  [confirmRoute()]: () => jsonResponse(CONFIRMED),
  [cancelRoute()]: () => jsonResponse(CANCELLED),
}
