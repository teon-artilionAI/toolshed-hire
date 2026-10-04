/**
 * Units, damage reports and hires for the SC-16 tests, shaped the way the
 * contract for damage and quarantine describes them.
 *
 * The unit that came back damaged is TSH-PC-0007, the first unit of the hire
 * in rental-samples.ts, which Thandi took out at Bellville. The counter
 * assistant in these tests is `COUNTER_STAFF`, who works there. As with the
 * other samples, the figures do not add up on purpose, so a screen that worked
 * one out for itself could not arrive at the one shown.
 */

import type { DamageReport, DamageReportPage, LocatedUnit, Rental } from '../shared/api/contract'
import { RENTAL_ID, RENTAL_REFERENCE } from './counter-samples'
import { ON_HIRE_UNIT } from './overview-samples'
import { WAITING_FOR_DAMAGE } from './rental-samples'

export const DAMAGE_REPORTS_ROUTE = 'GET /api/damage-reports'
export const FILE_DAMAGE_ROUTE = 'POST /api/damage-reports'

export function repairRoute(id: string): string {
  return `POST /api/damage-reports/${id}/repair`
}

export function resolutionRoute(id: string): string {
  return `POST /api/damage-reports/${id}/resolution`
}

/** The unit of the hire waiting for its damage report. */
export const DAMAGED_ITEM = WAITING_FOR_DAMAGE.items[0]

/** TSH-PC-0007 back at Bellville at C and quarantined by the return. */
export const QUARANTINED_AT_BELLVILLE: LocatedUnit = {
  ...ON_HIRE_UNIT,
  status: 'QUARANTINED',
  conditionGrade: 'C',
  dueBackOn: null,
  rentalReference: null,
}

/** A unit on the shelf at Bellville, where damage is found outside a hire. */
export const ON_THE_SHELF: LocatedUnit = {
  ...QUARANTINED_AT_BELLVILLE,
  assetTag: 'TSH-PC-0011',
  status: 'AVAILABLE',
  conditionGrade: 'A',
}

/** A unit held at Cape Town CBD, another branch than the assistant's. */
export const HELD_AT_CBD: LocatedUnit = {
  ...ON_THE_SHELF,
  assetTag: 'TSH-PC-0021',
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
}

/** A report filed outside a hire a while ago, still open. */
export const EARLIER_REPORT: DamageReport = {
  id: 'd4400000-0000-4000-8000-000000000001',
  reference: 'TSH-D-26-00012',
  assetTag: QUARANTINED_AT_BELLVILLE.assetTag,
  modelName: QUARANTINED_AT_BELLVILLE.modelName,
  branchCode: 'BLV',
  rentalId: null,
  rentalReference: null,
  rentalItemId: null,
  severity: 'MINOR',
  status: 'OPEN',
  description: 'Handle grip split along its length.',
  repairEstimate: '123.45',
  actualRepairCost: null,
  chargeableToCustomer: false,
  recoveryCharged: null,
  replacementValue: '7654.32',
  reportedAt: '2026-03-02T11:20:00+02:00',
  reportedByName: 'Thabo Ncube',
  resolvedAt: null,
  resolutionNotes: null,
}

/** A report that was closed as repaired. */
export const RESOLVED_REPORT: DamageReport = {
  ...EARLIER_REPORT,
  id: 'd4400000-0000-4000-8000-000000000002',
  reference: 'TSH-D-26-00009',
  status: 'RESOLVED',
  actualRepairCost: '98.76',
  resolvedAt: '2026-02-20T15:00:00+02:00',
  resolutionNotes: 'New grip fitted.',
}

/** The answer to filing a chargeable report for the unit of the hire. */
export const FILED_ON_THE_HIRE: DamageReport = {
  ...EARLIER_REPORT,
  id: 'd4400000-0000-4000-8000-000000000031',
  reference: 'TSH-D-26-00031',
  rentalId: RENTAL_ID,
  rentalReference: RENTAL_REFERENCE,
  rentalItemId: DAMAGED_ITEM.id,
  severity: 'MAJOR',
  description: 'Base plate cracked across the weld.',
  repairEstimate: '456.78',
  chargeableToCustomer: true,
  recoveryCharged: '321.09',
  replacementValue: '9876.54',
  reportedAt: '2026-03-12T10:20:00+02:00',
}

/** The answer to filing a report outside a hire. */
export const FILED_OFF_HIRE: DamageReport = {
  ...EARLIER_REPORT,
  id: 'd4400000-0000-4000-8000-000000000032',
  reference: 'TSH-D-26-00032',
  assetTag: ON_THE_SHELF.assetTag,
  chargeableToCustomer: true,
  reportedAt: '2026-03-12T10:20:00+02:00',
}

/** One page of reports, the way `GET /api/damage-reports` answers. */
export function reportPage(items: DamageReport[], overrides: Partial<DamageReportPage> = {}): DamageReportPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}

/** The hire once the report is filed. The deposit is settled, and the recovery
 *  is withheld from it. */
export const SETTLED_AFTER_DAMAGE: Rental = {
  ...WAITING_FOR_DAMAGE,
  status: 'SETTLED',
  items: [{ ...DAMAGED_ITEM, damageAssessment: 'DONE' }, WAITING_FOR_DAMAGE.items[1]],
  charges: [
    ...WAITING_FOR_DAMAGE.charges,
    {
      id: 'c3300000-0000-4000-8000-000000000031',
      type: 'DAMAGE_RECOVERY',
      description: 'Damage to TSH-PC-0007, TSH-D-26-00031',
      amountExVat: '279.21',
      vatRate: '15.00',
      vatAmount: '41.88',
      amountIncVat: '321.09',
      status: 'SETTLED',
      raisedAt: '2026-03-12T10:20:00+02:00',
      rentalItemId: DAMAGED_ITEM.id,
      reversesChargeId: null,
      reason: null,
    },
  ],
  depositWithheld: '765.53',
  depositRefunded: '4790.02',
  settledAt: '2026-03-12T10:20:00+02:00',
  settlementWaitingOn: null,
}
