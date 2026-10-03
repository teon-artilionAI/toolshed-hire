/**
 * The API answered by the spec itself, for the return screen, the overdue
 * worklist and the hire history.
 *
 * The accessibility scan and the narrow screen check of SC-15 and SC-18 need a
 * hire partly back with a late fee on it, and an overdue list with a unit in
 * the escalation queue. My Account needs a hire with every kind of charge. A
 * scan should not depend on what a database happens to hold, so these answers
 * stand in for the API, beside the other counter answers in counter-answers.ts.
 * They are shaped the way the contract for returns and settlement describes
 * them, with long names, which are what break a layout.
 */

import { dateFromToday } from './hire-dates.ts'

export const RETURN_RENTAL_ID = '9c3b1f2a-0000-4000-8000-000000000099'

const OVERDUE_RENTAL_ID = '9c3b1f2a-0000-4000-8000-000000000097'
const TWO_DAYS_AGO = dateFromToday(-2)
const SIXTEEN_DAYS_AGO = dateFromToday(-16)
const RETURNED_AT = `${dateFromToday(0)}T09:15:00+02:00`
const MODEL = 'CP 100 Plate Compactor with Water Tank'
const BREAKER = 'TE 1000-AVR Demolition Breaker'

function item(number: number, overrides: Record<string, unknown>) {
  return {
    id: `b2200000-0000-4000-8000-00000000000${number}`,
    assetTag: `TSH-PC-00${10 + number}`,
    modelName: MODEL,
    modelSlug: 'cp-100-plate-compactor',
    conditionOut: 'B',
    conditionIn: null,
    hourMeterOut: null,
    hourMeterIn: null,
    accessoriesOut: 'Water tank, two spare rubber mats and the long handle',
    accessoriesIn: null,
    returnedAt: null,
    daysLate: 0,
    lateFeePerDay: '220.00',
    daysLateToday: 2,
    lateFeeToday: '440.00',
    damageAssessment: 'NOT_NEEDED',
    ...overrides,
  }
}

function charge(number: number, overrides: Record<string, unknown>) {
  return {
    id: `c3300000-0000-4000-8000-00000000000${number}`,
    type: 'DEPOSIT_HOLD',
    description: 'Deposit held at collection',
    amountExVat: '4500.00',
    vatRate: '0.00',
    vatAmount: '0.00',
    amountIncVat: '4500.00',
    status: 'SETTLED',
    raisedAt: `${TWO_DAYS_AGO}T08:10:00+02:00`,
    rentalItemId: null,
    ...overrides,
  }
}

function rental(id: string, reference: string, overrides: Record<string, unknown>) {
  return {
    id,
    reference,
    status: 'OVERDUE',
    reservationId: '5f0c2a9e-0000-4000-8000-000000000124',
    reservationReference: 'TSH-R-26-000124',
    branchCode: 'CBD',
    branchName: 'Cape Town CBD',
    customerProfileId: '7a1d0c4e-0000-4000-8000-000000000301',
    customerName: 'Thandiwe Nomvula Mokoena-Hendricks',
    customerPhone: '0824417719',
    from: dateFromToday(-5),
    dueBackOn: TWO_DAYS_AGO,
    checkedOutAt: `${dateFromToday(-5)}T08:10:00+02:00`,
    returnedAt: null,
    items: [],
    charges: [charge(1, {})],
    depositHeld: '4500.00',
    depositWithheld: '0.00',
    depositRefunded: '0.00',
    balanceDue: '0.00',
    settledAt: null,
    agreementSigned: true,
    canReturn: true,
    settlementWaitingOn: 'ITEMS_OUT',
    ...overrides,
  }
}

/** One unit back two days late, one still out with an hour meter, one still out without. */
const PARTLY_BACK_ITEMS = [
  item(1, { conditionIn: 'B', accessoriesIn: 'Water tank and the long handle', returnedAt: RETURNED_AT, daysLate: 2, daysLateToday: 0, lateFeeToday: '0.00' }),
  item(2, { modelName: BREAKER, modelSlug: 'te-1000-avr-breaker', hourMeterOut: 1250 }),
  item(3, {}),
]

const PARTLY_BACK = rental(RETURN_RENTAL_ID, 'TSH-H-26-000099', {
  status: 'PARTIALLY_RETURNED',
  items: PARTLY_BACK_ITEMS,
  charges: [
    charge(1, {}),
    charge(2, { type: 'LATE_FEE', description: 'TSH-PC-0011 back 2 days late', amountExVat: '382.61', vatRate: '15.00', vatAmount: '57.39', amountIncVat: '440.00', rentalItemId: 'b2200000-0000-4000-8000-000000000001' }),
  ],
})

/** A hire sixteen days late, so its units are in the escalation queue. */
const LONG_OVERDUE = rental(OVERDUE_RENTAL_ID, 'TSH-H-26-000097', {
  customerName: 'Wesley Bartholomew Adonis-Vanderheyden',
  customerPhone: '0824417720',
  dueBackOn: SIXTEEN_DAYS_AGO,
  items: [item(4, { daysLateToday: 16, lateFeeToday: '3520.00' }), item(5, { daysLateToday: 16, lateFeeToday: '3520.00' })],
})

/** The same hire partly back, settled, the way a customer is sent it. */
const CUSTOMER_HIRE = rental(RETURN_RENTAL_ID, 'TSH-H-26-000099', {
  status: 'SETTLED',
  items: PARTLY_BACK_ITEMS.map((each) => ({ ...each, assetTag: null, returnedAt: RETURNED_AT, conditionIn: 'B' })),
  charges: [
    charge(1, {}),
    charge(2, { type: 'LATE_FEE', description: 'Late return of a plate compactor with water tank, 2 days', amountIncVat: '1320.00' }),
    charge(3, { type: 'DEPOSIT_RELEASE', description: 'Deposit released to the customer', amountExVat: '-3180.00', amountIncVat: '-3180.00' }),
  ],
  returnedAt: RETURNED_AT,
  depositWithheld: '1320.00',
  depositRefunded: '3180.00',
  settledAt: RETURNED_AT,
  canReturn: false,
  settlementWaitingOn: null,
})

/** What each staff route answers. */
export const RETURN_ANSWERS: Record<string, unknown> = {
  [`GET /api/rentals/${RETURN_RENTAL_ID}`]: PARTLY_BACK,
  'GET /api/rentals': { items: [LONG_OVERDUE, PARTLY_BACK], page: 1, pageSize: 20, total: 2 },
}

/** What `GET /api/me/rentals` answers for the customer on My Account. */
export const MY_RENTALS = { items: [CUSTOMER_HIRE], page: 1, pageSize: 5, total: 1 }
