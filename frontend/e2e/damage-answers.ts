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
 */

import { dateFromToday } from './hire-dates.ts'

/** The unit the scans open, which the locator answer finds at Cape Town CBD. */
const DAMAGED_TAG = 'TSH-PC-0007'

/** The unit of the hire it came back on. */
const RENTAL_ITEM_ID = 'b2200000-0000-4000-8000-000000000002'

/** SC-16 for that unit, reached from its return. */
export const DAMAGE_PATH = `/counter/damage/${DAMAGED_TAG}?rentalItem=${RENTAL_ITEM_ID}`

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

/** What each damage route answers. */
export const DAMAGE_ANSWERS: Record<string, unknown> = {
  'GET /api/damage-reports': REPORTS,
}
