/**
 * The API answered by the spec itself, for the damage screen.
 *
 * The accessibility scan and the narrow screen check of SC-16 need a unit that
 * came back on a hire and reports already on it, one open and one closed. A
 * scan should not depend on what a database happens to hold, so these answers
 * stand in for the API, beside the other counter answers in
 * counter-answers.ts. The unit is found through the locator answer in
 * overview-answers.ts. They are shaped the way the contract for damage and
 * quarantine describes them, with long words, which are what break a layout.
 * Each report has photographs, whose answers are built in photo-answers.ts.
 */

import { dateFromToday } from './hire-dates.ts'
import { photo, photoList } from './photo-answers.ts'
import { RETURN_RENTAL_ID } from './return-answers.ts'

/** The unit the scans open, which the locator answer finds at Cape Town CBD. */
const DAMAGED_TAG = 'TSH-PC-0007'

/** The unit of the hire it came back on. */
const RENTAL_ITEM_ID = 'b2200000-0000-4000-8000-000000000002'

/** SC-16 for that unit, reached from its return, which names the hire and its
 *  unit. The screen reads the hire for the replacement value of the unit. */
export const DAMAGE_PATH = `/counter/damage/${DAMAGED_TAG}?rental=${RETURN_RENTAL_ID}&rentalItem=${RENTAL_ITEM_ID}`

/** The open report on the unit, and the closed one under it. */
export const OPEN_REPORT_ID = 'd4400000-0000-4000-8000-000000000002'
export const OPEN_REPORT_REFERENCE = 'TSH-D-26-00012'
export const CLOSED_REPORT_ID = 'd4400000-0000-4000-8000-000000000001'
const CLOSED_REPORT_REFERENCE = 'TSH-D-26-00011'

/** The route of the photographs of a report. */
export function photosRoute(reportId: string): string {
  return `GET /api/damage-reports/${reportId}/photos`
}

function report(number: number, overrides: Record<string, unknown>) {
  return {
    id: `d4400000-0000-4000-8000-00000000000${number}`,
    reference: `TSH-D-26-0001${number}`,
    assetTag: DAMAGED_TAG,
    modelName: 'CP 100 Plate Compactor with Water Tank',
    branchCode: 'CBD',
    rentalId: null,
    rentalReference: null,
    rentalItemId: null,
    severity: 'MINOR',
    status: 'OPEN',
    description:
      'Water tank bracket cracked along the weld where it meets the handle frame, and the tank now rattles under load.',
    repairEstimate: '1450.00',
    actualRepairCost: null,
    chargeableToCustomer: false,
    recoveryCharged: null,
    replacementValue: '42500.00',
    reportedAt: `${dateFromToday(-3)}T11:20:00+02:00`,
    reportedByName: 'Elmarie Fourie-Vanderwesthuizen',
    resolvedAt: null,
    resolutionNotes: null,
    ...overrides,
  }
}

const REPORTS = {
  items: [
    report(2, {}),
    report(1, {
      severity: 'MAJOR',
      status: 'RESOLVED',
      rentalId: '9c3b1f2a-0000-4000-8000-000000000097',
      rentalReference: 'TSH-H-26-000097',
      rentalItemId: 'b2200000-0000-4000-8000-000000000004',
      chargeableToCustomer: true,
      recoveryCharged: '1150.00',
      actualRepairCost: '980.00',
      resolvedAt: `${dateFromToday(-1)}T15:00:00+02:00`,
      resolutionNotes: 'New base plate welded on and the vibration dampers replaced.',
    }),
  ],
  page: 1,
  pageSize: 20,
  total: 2,
}

/** The two photographs of the open report, oldest first. */
export const OPEN_REPORT_PHOTOS = [1, 2].map((number) => photo(OPEN_REPORT_ID, OPEN_REPORT_REFERENCE, number))

/** What each damage route answers. Both reports have photographs, so every
 *  scan of the screen sees them listed. */
export const DAMAGE_ANSWERS: Record<string, unknown> = {
  'GET /api/damage-reports': REPORTS,
  [photosRoute(OPEN_REPORT_ID)]: photoList(OPEN_REPORT_PHOTOS),
  [photosRoute(CLOSED_REPORT_ID)]: photoList([photo(CLOSED_REPORT_ID, CLOSED_REPORT_REFERENCE, 1)]),
}
