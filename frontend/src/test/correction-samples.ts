/**
 * The owner's corrections for tests. A hire with a charge of every standing,
 * the hires the server answers each correction with, a checkout short of a
 * unit, and the routes of the writes. Shaped the way the contract for the
 * admin operations describes them.
 *
 * The hire starts from `SETTLED_HIRE` in rental-samples.ts, Thandi's hire at
 * Bellville, and the checkout from `READY_CHECKOUT` in counter-samples.ts. As
 * with the other samples, the figures do not add up on purpose, so a screen
 * that worked a balance out for itself could not arrive at the one shown.
 */

import type { Rental, RentalCharge, Reservation, ReservationCheckout } from '../shared/api/contract'
import { COUNTER_CONFIRMED, READY_CHECKOUT, RENTAL_ID } from './counter-samples'
import { LATE_FEE_CHARGE, SETTLED_HIRE } from './rental-samples'
import { RESERVATION_ID } from './reservation-samples'

export function waiverRoute(chargeId: string): string {
  return `POST /api/admin/charges/${chargeId}/waiver`
}

export function reversalRoute(chargeId: string): string {
  return `POST /api/admin/charges/${chargeId}/reversal`
}

export function adjustmentRoute(rentalId: string = RENTAL_ID): string {
  return `POST /api/admin/rentals/${rentalId}/adjustments`
}

export function releaseRoute(allocationId: string): string {
  return `POST /api/admin/allocations/${allocationId}/release`
}

export function reallocationRoute(reservationId: string = RESERVATION_ID): string {
  return `POST /api/reservations/${reservationId}/reallocation`
}

/** The hire charge, settled at the counter when the equipment went out. */
export const HIRE_CHARGE: RentalCharge = {
  ...LATE_FEE_CHARGE,
  id: 'c3300000-0000-4000-8000-000000000010',
  type: 'HIRE',
  description: 'CP 100 Plate Compactor, 2 units for 1 day',
  amountExVat: '3864.73',
  vatAmount: '579.71',
  amountIncVat: '4444.44',
  status: 'SETTLED',
  raisedAt: '2026-03-12T08:10:00+02:00',
  rentalItemId: null,
}

/** The late fee, not settled yet. */
export const PENDING_LATE_FEE: RentalCharge = { ...LATE_FEE_CHARGE, status: 'PENDING' }

/** A hire with a settled hire charge and a pending late fee. */
export const CORRECTABLE_HIRE: Rental = {
  ...SETTLED_HIRE,
  status: 'RETURNED',
  charges: [SETTLED_HIRE.charges[0], HIRE_CHARGE, PENDING_LATE_FEE],
  balanceDue: '444.44',
  settledAt: null,
  settlementWaitingOn: 'BALANCE_PAYMENT',
}

/** What the owner wrote for each correction. */
export const REVERSAL_REASON = 'Charged twice for the same day'
export const WAIVER_REASON = 'Traffic accident on the N1'
export const ADJUSTMENT_REASON = 'Goodwill for the late delivery'

/** The reversal of the hire charge, the amounts the other way. */
export const HIRE_REVERSAL: RentalCharge = {
  ...HIRE_CHARGE,
  id: 'c3300000-0000-4000-8000-000000000011',
  description: 'Reversal of the hire charge',
  amountExVat: '-3864.73',
  vatAmount: '-579.71',
  amountIncVat: '-4444.44',
  raisedAt: '2026-03-12T11:00:00+02:00',
  reversesChargeId: HIRE_CHARGE.id,
  reason: REVERSAL_REASON,
}

/** The hire the reversal answers with. The balance is the server's, not a sum. */
export const AFTER_REVERSAL: Rental = {
  ...CORRECTABLE_HIRE,
  charges: [...CORRECTABLE_HIRE.charges, HIRE_REVERSAL],
  balanceDue: '0.00',
}

/** The hire the waiver of the late fee answers with. */
export const AFTER_WAIVER: Rental = {
  ...CORRECTABLE_HIRE,
  status: 'SETTLED',
  charges: [SETTLED_HIRE.charges[0], HIRE_CHARGE, { ...PENDING_LATE_FEE, status: 'WAIVED', reason: WAIVER_REASON }],
  balanceDue: '0.00',
  settledAt: '2026-03-12T11:00:00+02:00',
  settlementWaitingOn: null,
}

/** The hire the adjustment answers with. */
export const AFTER_ADJUSTMENT: Rental = {
  ...CORRECTABLE_HIRE,
  charges: [
    ...CORRECTABLE_HIRE.charges,
    {
      ...HIRE_CHARGE,
      id: 'c3300000-0000-4000-8000-000000000012',
      type: 'ADJUSTMENT',
      description: 'Adjustment by the owner',
      amountExVat: '-130.43',
      vatAmount: '-19.57',
      amountIncVat: '-150.00',
      raisedAt: '2026-03-12T11:00:00+02:00',
      reason: ADJUSTMENT_REASON,
    },
  ],
  balanceDue: '294.44',
}

const [FIRST_UNIT, SECOND_UNIT] = READY_CHECKOUT.units

/** The checkout once the owner released the first unit. It cannot go out, and
 *  the server says why. */
export const SHORT_CHECKOUT: ReservationCheckout = {
  ...READY_CHECKOUT,
  units: [SECOND_UNIT],
  canCheckOut: false,
  refusal: 'TSH-R-26-000124 is 1 unit short, so it cannot go out until it is reallocated.',
  unitsShort: 1,
}

/** The booking the reallocation answers with, with a new unit in place of the first. */
export const REALLOCATED: Reservation = {
  ...COUNTER_CONFIRMED,
  lines: COUNTER_CONFIRMED.lines.map((line) => ({ ...line, assetTags: ['TSH-PC-0012', 'TSH-PC-0011'] })),
}

/** The unit the owner releases in the tests. */
export const RELEASED_UNIT = FIRST_UNIT
