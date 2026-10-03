/**
 * The API answered by the spec itself, for the counter's dashboard, diary and
 * locator.
 *
 * The accessibility scan and the narrow screen check of SC-10, SC-11 and SC-17
 * need a day with something on it and a search that finds units. A scan should
 * not depend on what a database happens to hold, so these answers stand in for
 * the API, beside the other counter answers in counter-answers.ts. They are
 * shaped the way the contract for the counter overview describes them, with
 * long names, which are what break a layout. Every route is keyed by its path
 * alone, so the diary answers with the same day whatever it is asked.
 */

import { dateFromToday } from './hire-dates.ts'

const TODAY = dateFromToday(0)
const TOMORROW = dateFromToday(1)
const TWO_DAYS_AGO = dateFromToday(-2)

const CUSTOMER_NAME = 'Thandiwe Nomvula Mokoena-Hendricks'
const SECOND_CUSTOMER_NAME = 'Wesley Bartholomew Adonis-Vanderheyden'
const LONG_SUMMARY = '2 x CP 100 Plate Compactor with Water Tank, 1 x TE 1000-AVR Demolition Breaker'

const DASHBOARD = {
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  date: TODAY,
  counts: { collectionsDue: 1, returnsDue: 1, overdue: 1, onHire: 27, quarantined: 3 },
  collectionsDue: [
    { reservationId: '5f0c2a9e-0000-4000-8000-000000000124', reference: 'TSH-R-26-000124', customerName: CUSTOMER_NAME, customerPhone: '0824417719', from: TODAY, to: TOMORROW, unitCount: 3, summary: LONG_SUMMARY },
  ],
  returnsDue: [
    { rentalId: '9c3b1f2a-0000-4000-8000-000000000099', reference: 'TSH-H-26-000099', customerName: SECOND_CUSTOMER_NAME, customerPhone: '0824417720', dueBackOn: TODAY, itemsOut: 1, itemCount: 3, summary: LONG_SUMMARY },
  ],
  overdue: [
    { rentalId: '9c3b1f2a-0000-4000-8000-000000000097', reference: 'TSH-H-26-000097', customerName: CUSTOMER_NAME, customerPhone: '0731112233', dueBackOn: TWO_DAYS_AGO, daysOverdue: 2, itemsOut: 2, lateFeeAccrued: '1240.00' },
  ],
}

const DIARY = {
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  days: [
    {
      date: TODAY,
      collections: [
        { reservationId: '5f0c2a9e-0000-4000-8000-000000000124', reference: 'TSH-R-26-000124', status: 'CONFIRMED', customerName: CUSTOMER_NAME, customerPhone: '0824417719', from: TODAY, to: TOMORROW, unitCount: 3, summary: LONG_SUMMARY, canMarkNoShow: true },
        { reservationId: '5f0c2a9e-0000-4000-8000-000000000125', reference: 'TSH-R-26-000125', status: 'COLLECTED', customerName: SECOND_CUSTOMER_NAME, customerPhone: '0824417720', from: TODAY, to: TOMORROW, unitCount: 1, summary: '1 x CP 100 Plate Compactor with Water Tank', canMarkNoShow: false },
      ],
      returns: [
        { rentalId: '9c3b1f2a-0000-4000-8000-000000000099', reference: 'TSH-H-26-000099', status: 'OVERDUE', customerName: SECOND_CUSTOMER_NAME, customerPhone: '0824417720', dueBackOn: TODAY, itemsOut: 1, itemCount: 3, summary: LONG_SUMMARY },
      ],
    },
  ],
}

const LOCATED = {
  items: [
    { assetTag: 'TSH-PC-0007', modelName: 'CP 100 Plate Compactor with Water Tank', modelSlug: 'cp-100-plate-compactor', categoryName: 'Compaction and Earthmoving', branchCode: 'CBD', branchName: 'Cape Town CBD', status: 'ON_HIRE', conditionGrade: 'B', dueBackOn: TOMORROW, rentalReference: 'TSH-H-26-000099' },
    { assetTag: 'TSH-PC-0021', modelName: 'CP 100 Plate Compactor with Water Tank', modelSlug: 'cp-100-plate-compactor', categoryName: 'Compaction and Earthmoving', branchCode: 'SMW', branchName: 'Somerset West', status: 'AVAILABLE', conditionGrade: 'A', dueBackOn: null, rentalReference: null },
    { assetTag: 'TSH-DR-0045', modelName: 'GBH 2-26 DRE Rotary Hammer', modelSlug: 'gbh-2-26-dre-rotary-hammer', categoryName: 'Breaking and Drilling', branchCode: 'BLV', branchName: 'Bellville', status: 'QUARANTINED', conditionGrade: 'C', dueBackOn: null, rentalReference: null },
  ],
  page: 1,
  pageSize: 20,
  total: 3,
}

/** What each overview route answers. */
export const OVERVIEW_ANSWERS: Record<string, unknown> = {
  'GET /api/counter/dashboard': DASHBOARD,
  'GET /api/counter/diary': DIARY,
  'GET /api/assets/locator': LOCATED,
}
