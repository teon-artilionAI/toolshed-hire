/**
 * The counter's day and the locator, for tests, shaped the way the contract
 * for the counter overview describes them.
 *
 * The counter assistant is `COUNTER_STAFF` from session-samples.ts, who works
 * at Bellville, and the clock of the tests that use these is pinned to
 * `TEST_NOW`, so today is `TEST_TODAY`, a Thursday.
 *
 * The figures do not add up on purpose. The late fee is not two days of any
 * rate, so a screen that worked one out for itself could not arrive at it.
 */

import type {
  BranchDiary,
  CounterDashboard,
  DiaryCollection,
  DiaryDay,
  DiaryReturn,
  LocatedUnit,
  LocatorPage,
  Reservation,
} from '../shared/api/contract'
import { TEST_TODAY } from './catalogue-samples'
import { COUNTER_CONFIRMED, DAY_AFTER_TODAY, RENTAL_ID, RENTAL_REFERENCE, THANDI, WESLEY } from './counter-samples'
import { REFERENCE, RESERVATION_ID, SECOND_REFERENCE, SECOND_RESERVATION_ID } from './reservation-samples'

export const DASHBOARD_ROUTE = 'GET /api/counter/dashboard'
export const DIARY_ROUTE = 'GET /api/counter/diary'
export const LOCATOR_ROUTE = 'GET /api/assets/locator'

export function noShowRoute(id: string = RESERVATION_ID): string {
  return `POST /api/reservations/${id}/no-show`
}

export const OVERDUE_RENTAL_ID = '9c3b1f2a-0000-4000-8000-000000000097'
export const OVERDUE_REFERENCE = 'TSH-H-26-000097'
export const MONDAY_OF_THIS_WEEK = '2026-03-09'
export const MONDAY_OF_NEXT_WEEK = '2026-03-16'

/** Two days late, with a fee no rate would give. */
export const ODD_LATE_FEE = '333.33'

/** Everything due at Bellville today, with the true counts above the lists. */
export const DASHBOARD: CounterDashboard = {
  branchCode: 'BLV',
  branchName: 'Bellville',
  date: TEST_TODAY,
  counts: { collectionsDue: 1, returnsDue: 1, overdue: 1, onHire: 14, quarantined: 2 },
  collectionsDue: [
    {
      reservationId: RESERVATION_ID,
      reference: REFERENCE,
      customerName: THANDI.displayName,
      customerPhone: THANDI.phone,
      from: TEST_TODAY,
      to: DAY_AFTER_TODAY,
      unitCount: 2,
      summary: '2 x CP 100 Plate Compactor',
    },
  ],
  returnsDue: [
    {
      rentalId: RENTAL_ID,
      reference: RENTAL_REFERENCE,
      customerName: WESLEY.displayName,
      customerPhone: WESLEY.phone,
      dueBackOn: TEST_TODAY,
      itemsOut: 1,
      itemCount: 2,
      summary: '2 x TE 1000-AVR Breaker',
    },
  ],
  overdue: [
    {
      rentalId: OVERDUE_RENTAL_ID,
      reference: OVERDUE_REFERENCE,
      customerName: 'Sipho Ndlovu',
      customerPhone: '0731112233',
      dueBackOn: '2026-03-10',
      daysOverdue: 2,
      itemsOut: 1,
      lateFeeAccrued: ODD_LATE_FEE,
    },
  ],
}

/** A day with nothing to collect, take back or chase, and units still out. */
export const QUIET_DASHBOARD: CounterDashboard = {
  ...DASHBOARD,
  counts: { collectionsDue: 0, returnsDue: 0, overdue: 0, onHire: 3, quarantined: 0 },
  collectionsDue: [],
  returnsDue: [],
  overdue: [],
}

/** Thandi's booking, confirmed and due out today. The server says it may be
 *  marked as a no show. */
export const DUE_OUT: DiaryCollection = {
  reservationId: RESERVATION_ID,
  reference: REFERENCE,
  status: 'CONFIRMED',
  customerName: THANDI.displayName,
  customerPhone: THANDI.phone,
  from: TEST_TODAY,
  to: DAY_AFTER_TODAY,
  unitCount: 2,
  summary: '2 x CP 100 Plate Compactor',
  canMarkNoShow: true,
}

/** Wesley's booking, already collected today. */
export const COLLECTED_TODAY: DiaryCollection = {
  ...DUE_OUT,
  reservationId: SECOND_RESERVATION_ID,
  reference: SECOND_REFERENCE,
  status: 'COLLECTED',
  customerName: WESLEY.displayName,
  customerPhone: WESLEY.phone,
  summary: '1 x Trench Rammer',
  unitCount: 1,
  canMarkNoShow: false,
}

/** A hire due back today, with one of its two units still out. */
export const DUE_BACK: DiaryReturn = {
  rentalId: RENTAL_ID,
  reference: RENTAL_REFERENCE,
  status: 'OPEN',
  customerName: WESLEY.displayName,
  customerPhone: WESLEY.phone,
  dueBackOn: TEST_TODAY,
  itemsOut: 1,
  itemCount: 2,
  summary: '2 x TE 1000-AVR Breaker',
}

/** A day with nothing on it. */
export function emptyDay(date: string): DiaryDay {
  return { date, collections: [], returns: [] }
}

/** The diary at Bellville for the days given. */
export function diaryOf(days: DiaryDay[]): BranchDiary {
  return { branchCode: 'BLV', branchName: 'Bellville', days }
}

/** Today at Bellville, with two bookings going out and one hire coming back. */
export const TODAY_IN_THE_DIARY = diaryOf([
  { date: TEST_TODAY, collections: [DUE_OUT, COLLECTED_TODAY], returns: [DUE_BACK] },
])

/** The answer of the no show. Thandi's booking, now a no show. */
export const MARKED_NO_SHOW: Reservation = {
  ...COUNTER_CONFIRMED,
  status: 'NO_SHOW',
  canCancel: false,
}

/** A unit out on hire at Bellville. */
export const ON_HIRE_UNIT: LocatedUnit = {
  assetTag: 'TSH-PC-0007',
  modelName: 'CP 100 Plate Compactor',
  modelSlug: 'cp-100-plate-compactor',
  categoryName: 'Compaction',
  branchCode: 'BLV',
  branchName: 'Bellville',
  status: 'ON_HIRE',
  conditionGrade: 'B',
  dueBackOn: DAY_AFTER_TODAY,
  rentalReference: RENTAL_REFERENCE,
}

/** A unit on the shelf at Cape Town CBD. */
export const SHELF_UNIT: LocatedUnit = {
  ...ON_HIRE_UNIT,
  assetTag: 'TSH-PC-0021',
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  status: 'AVAILABLE',
  conditionGrade: 'A',
  dueBackOn: null,
  rentalReference: null,
}

/** A unit withdrawn from hire at Somerset West. */
export const QUARANTINED_UNIT: LocatedUnit = {
  ...SHELF_UNIT,
  assetTag: 'TSH-DR-0045',
  modelName: 'GBH 2-26 DRE Rotary Hammer',
  modelSlug: 'gbh-2-26-dre-rotary-hammer',
  categoryName: 'Breaking and drilling',
  branchCode: 'SMW',
  branchName: 'Somerset West',
  status: 'QUARANTINED',
  conditionGrade: 'C',
}

/** One page of units, the way `GET /api/assets/locator` answers. */
export function locatorPage(items: LocatedUnit[], overrides: Partial<LocatorPage> = {}): LocatorPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
