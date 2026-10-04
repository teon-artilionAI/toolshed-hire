/**
 * Hires for tests, at each point of a return, shaped the way the contract for
 * returns and settlement describes them.
 *
 * They start from `RENTAL` in counter-samples.ts, the hire Thandi took out at
 * Bellville with two plate compactors. The counter assistant in these tests is
 * `COUNTER_STAFF`, who works there. The clock of the tests that use them is
 * pinned to `TEST_NOW`.
 *
 * As with the other samples, the figures do not add up on purpose. The late fee
 * is not two days of the daily rate, and what was released is not what was
 * held less what was withheld, so a screen that worked a figure out for itself
 * could not arrive at the one shown.
 */

import type { Rental, RentalCharge, RentalItem, RentalPage } from '../shared/api/contract'
import { RENTAL, RENTAL_ID } from './counter-samples'

export const RENTALS_ROUTE = 'GET /api/rentals'
export const MY_RENTALS_ROUTE = 'GET /api/me/rentals'

export function rentalRoute(idOrReference: string = RENTAL_ID): string {
  return `GET /api/rentals/${idOrReference}`
}

export function returnsRoute(id: string = RENTAL_ID): string {
  return `POST /api/rentals/${id}/returns`
}

export function balanceRoute(id: string = RENTAL_ID): string {
  return `POST /api/rentals/${id}/balance-payment`
}

export function lossRoute(itemId: string, id: string = RENTAL_ID): string {
  return `POST /api/rentals/${id}/items/${itemId}/loss`
}

const [FIRST_ITEM, SECOND_ITEM] = RENTAL.items

/** The first unit, TSH-PC-0007, which has an hour meter and went out at B. */
export const METERED: RentalItem = FIRST_ITEM

/** The second unit, TSH-PC-0011, with no hour meter, which went out at A. */
export const UNMETERED: RentalItem = SECOND_ITEM

/** Two days late, with a fee no rate would give. */
export const ODD_FEE_TODAY = '333.33'

/** Both units out, two days past the day they were due back. */
export const OVERDUE_HIRE: Rental = {
  ...RENTAL,
  status: 'OVERDUE',
  items: RENTAL.items.map((item) => ({ ...item, daysLateToday: 2, lateFeeToday: ODD_FEE_TODAY })),
}

const RETURNED_AT = '2026-03-12T10:15:00+02:00'

function charge(id: string, overrides: Partial<RentalCharge>): RentalCharge {
  return {
    id: `c3300000-0000-4000-8000-00000000000${id}`,
    type: 'LATE_FEE',
    description: 'Late return',
    amountExVat: '0.00',
    vatRate: '15.00',
    vatAmount: '0.00',
    amountIncVat: '0.00',
    status: 'SETTLED',
    raisedAt: RETURNED_AT,
    rentalItemId: null,
    reversesChargeId: null,
    reason: null,
    ...overrides,
  }
}

const [DEPOSIT_HOLD] = RENTAL.charges

/** The late fee the server raised for the first unit. */
export const LATE_FEE_CHARGE = charge('2', {
  type: 'LATE_FEE',
  description: 'TSH-PC-0007 back 2 days late',
  amountExVat: '386.47',
  vatAmount: '57.97',
  amountIncVat: '444.44',
  rentalItemId: FIRST_ITEM.id,
})

/** What was given back of the deposit. A release is a negative amount. */
export const RELEASE_CHARGE = charge('3', {
  type: 'DEPOSIT_RELEASE',
  description: 'Deposit released',
  vatRate: '0.00',
  amountExVat: '-4999.99',
  amountIncVat: '-4999.99',
})

/** The first unit back at B, two days late. The second still out. */
export const PARTLY_BACK: Rental = {
  ...OVERDUE_HIRE,
  status: 'PARTIALLY_RETURNED',
  items: [
    { ...OVERDUE_HIRE.items[0], conditionIn: 'B', hourMeterIn: 1262, returnedAt: RETURNED_AT, daysLate: 2 },
    OVERDUE_HIRE.items[1],
  ],
  charges: [DEPOSIT_HOLD, LATE_FEE_CHARGE],
}

/** Both units back, and the deposit settled. */
export const SETTLED_HIRE: Rental = {
  ...PARTLY_BACK,
  status: 'SETTLED',
  items: [
    PARTLY_BACK.items[0],
    { ...PARTLY_BACK.items[1], conditionIn: 'A', returnedAt: RETURNED_AT, daysLate: 2, daysLateToday: 0, lateFeeToday: '0.00' },
  ],
  charges: [DEPOSIT_HOLD, LATE_FEE_CHARGE, RELEASE_CHARGE],
  returnedAt: RETURNED_AT,
  depositWithheld: '444.44',
  depositRefunded: '4999.99',
  balanceDue: '0.00',
  settledAt: RETURNED_AT,
  canReturn: false,
  settlementWaitingOn: null,
}

/** Both units back, and the charges came to more than the deposit. A charge the
 *  deposit covered only in part stays pending until the balance is paid. */
export const OWES_A_BALANCE: Rental = {
  ...SETTLED_HIRE,
  status: 'RETURNED',
  charges: [DEPOSIT_HOLD, { ...LATE_FEE_CHARGE, status: 'PENDING' }],
  depositRefunded: '0.00',
  balanceDue: '777.77',
  settledAt: null,
  settlementWaitingOn: 'BALANCE_PAYMENT',
}

/** Both units back, and the first one is waiting for its damage report. */
export const WAITING_FOR_DAMAGE: Rental = {
  ...OWES_A_BALANCE,
  items: [{ ...OWES_A_BALANCE.items[0], conditionIn: 'C', damageAssessment: 'REQUIRED' }, OWES_A_BALANCE.items[1]],
  balanceDue: '0.00',
  settlementWaitingOn: 'DAMAGE_ASSESSMENT',
}

/** Both units out sixteen days past their due date, so in the escalation queue. */
export const ESCALATED_HIRE: Rental = {
  ...OVERDUE_HIRE,
  items: OVERDUE_HIRE.items.map((item) => ({ ...item, daysLateToday: 16, lateFeeToday: '1919.19' })),
}

/** When the loss of the first unit was recorded. */
export const LOST_AT = '2026-03-29T09:05:00+02:00'

/**
 * The hire the loss of the first unit answers with. The API closes a lost unit
 * with the time of the loss and no grade, and the charges for it carry its id.
 * The second unit is still out past its due date, so the hire stays overdue.
 */
export const AFTER_THE_LOSS: Rental = {
  ...ESCALATED_HIRE,
  items: [
    { ...ESCALATED_HIRE.items[0], returnedAt: LOST_AT, daysLate: 16, daysLateToday: 0, lateFeeToday: '0.00' },
    ESCALATED_HIRE.items[1],
  ],
  charges: [
    DEPOSIT_HOLD,
    charge('4', { type: 'LATE_FEE', description: 'Fourteen days of late fee', amountIncVat: '1680.00', status: 'PENDING', rentalItemId: FIRST_ITEM.id }),
    charge('5', { type: 'DEPOSIT_FORFEIT', description: 'Deposit forfeited for TSH-PC-0007', vatRate: '0.00', amountIncVat: '1500.00', rentalItemId: FIRST_ITEM.id }),
    charge('6', { type: 'DAMAGE_RECOVERY', description: 'Recovery of TSH-PC-0007', amountIncVat: '8888.88', status: 'PENDING', rentalItemId: FIRST_ITEM.id }),
  ],
  balanceDue: '0.00',
}

/**
 * The hire the loss answers with when the lost unit was the last one out. The
 * server settles the deposit as it records the loss, and what the deposit could
 * not cover is the balance due.
 */
export const LOST_THE_LAST_UNIT: Rental = {
  ...AFTER_THE_LOSS,
  status: 'RETURNED',
  items: [AFTER_THE_LOSS.items[0], SETTLED_HIRE.items[1]],
  returnedAt: LOST_AT,
  depositWithheld: '5555.55',
  balanceDue: '6543.21',
  canReturn: false,
  settlementWaitingOn: 'BALANCE_PAYMENT',
}

/** What the server writes on the late fee for a customer, who is never told a tag. */
export const CUSTOMER_LATE_FEE_DESCRIPTION = 'Plate compactor back 2 days late'

/** A hire the way a customer is sent it, with no tag or replacement value on
 *  any unit and no tag on any charge. */
export const CUSTOMER_HIRE: Rental = {
  ...SETTLED_HIRE,
  items: SETTLED_HIRE.items.map((item) => ({ ...item, assetTag: null, replacementValue: null })),
  charges: SETTLED_HIRE.charges.map((each) =>
    each.type === 'LATE_FEE' ? { ...each, description: CUSTOMER_LATE_FEE_DESCRIPTION } : each,
  ),
}

/** One page of hires, the way both lists answer. */
export function rentalPage(items: Rental[], overrides: Partial<RentalPage> = {}): RentalPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
