/**
 * The owner's asset register for tests, shaped the way the contract for the
 * asset register describes it.
 *
 * Three units. One just registered at intake, one on the shelf with a serial
 * number, a meter, notes, a booking holding it and two open damage reports,
 * and one retired with nothing left to do. Each answers its own read with a
 * history that has one entry of every kind.
 */

import type { AdminAsset, AdminAssetDetail, AdminAssetPage, AssetHistoryEntry } from '../shared/api/contract'
import { BREAKER, HAMMER } from './admin-catalogue-samples'

export const ASSETS_ROUTE = 'GET /api/admin/assets'
export const REGISTER_ROUTE = 'POST /api/admin/assets'

export function assetRoute(tag: string, method: 'GET' | 'PATCH' = 'GET'): string {
  return `${method} /api/admin/assets/${tag}`
}

export function moveRoute(tag: string): string {
  return `POST /api/admin/assets/${tag}/transitions`
}

/** Just registered. It can be commissioned or quarantined. */
export const INTAKE_UNIT: AdminAsset = {
  id: 'a55e7000-0000-4000-8000-000000000047',
  assetTag: 'TSH-DR-0047',
  modelId: HAMMER.id,
  modelName: HAMMER.name,
  modelSlug: HAMMER.slug,
  categoryName: HAMMER.categoryName,
  branchCode: 'CBD',
  branchName: 'Cape Town CBD',
  serialNumber: null,
  status: 'INTAKE',
  conditionGrade: 'A',
  acquiredOn: '2026-03-10',
  acquisitionCost: '3980.00',
  hourMeterReading: null,
  notes: null,
  retiredOn: null,
  activeAllocationCount: 0,
  openDamageReports: 0,
  allowedTransitions: ['AVAILABLE', 'QUARANTINED'],
}

/** On the shelf, held by a booking, with two damage reports still open. */
export const SHELF_UNIT: AdminAsset = {
  ...INTAKE_UNIT,
  id: 'a55e7000-0000-4000-8000-000000000042',
  assetTag: 'TSH-DR-0042',
  branchCode: 'BLV',
  branchName: 'Bellville',
  serialNumber: 'GBH-778812',
  status: 'AVAILABLE',
  conditionGrade: 'B',
  acquiredOn: '2024-06-11',
  hourMeterReading: 412,
  notes: 'Chuck replaced in January.',
  activeAllocationCount: 1,
  openDamageReports: 2,
  allowedTransitions: ['QUARANTINED', 'UNDER_REPAIR', 'RETIRED'],
}

/** Retired, and so with no move left. */
export const RETIRED_UNIT: AdminAsset = {
  ...INTAKE_UNIT,
  id: 'a55e7000-0000-4000-8000-000000000003',
  assetTag: 'TSH-BR-0003',
  modelId: BREAKER.id,
  modelName: BREAKER.name,
  modelSlug: BREAKER.slug,
  categoryName: BREAKER.categoryName,
  branchCode: 'SMW',
  branchName: 'Somerset West',
  status: 'RETIRED',
  conditionGrade: 'C',
  acquisitionCost: '18500.00',
  retiredOn: '2026-02-28',
  allowedTransitions: [],
}

export const BOOKING_REFERENCE = 'TSH-R-26-000124'
export const HIRE_REFERENCE = 'TSH-H-26-000099'
export const REPORT_REFERENCE = 'TSH-D-26-00031'

/** One entry of every kind, the newest first. */
export const HISTORY: AssetHistoryEntry[] = [
  { at: '2026-03-11T09:15:00+02:00', kind: 'ALLOCATION', summary: `Held for booking ${BOOKING_REFERENCE} from 2026-03-14 to 2026-03-16.`, reference: BOOKING_REFERENCE },
  { at: '2026-03-02T16:40:00+02:00', kind: 'DAMAGE_REPORT', summary: `Damage report ${REPORT_REFERENCE} filed for minor damage.`, reference: REPORT_REFERENCE },
  { at: '2026-02-20T08:05:00+02:00', kind: 'RENTAL', summary: `Handed over on hire ${HIRE_REFERENCE} in grade B, due back 2026-02-23.`, reference: HIRE_REFERENCE },
  { at: '2024-06-11T10:00:00+02:00', kind: 'AUDIT_EVENT', summary: 'Registered in the fleet at INTAKE.', reference: null },
]

export function detailOf(unit: AdminAsset, history: AssetHistoryEntry[] = HISTORY): AdminAssetDetail {
  return { ...unit, history }
}

export function assetPage(
  items: AdminAsset[] = [SHELF_UNIT, INTAKE_UNIT, RETIRED_UNIT],
  overrides: Partial<AdminAssetPage> = {},
): AdminAssetPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
