/**
 * The asset register wire types. Every unit of the fleet as the owner keeps
 * it, retired or not, with its paperwork, where it stands in its lifecycle,
 * the moves it may make by hand and its history.
 *
 * These are written by hand from the contract for branch 020, because the
 * backend half of the change is built at the same time and the OpenAPI
 * document does not describe these routes yet. Once it does, `npm run
 * api:types` brings them into schema.d.ts and each type here is rebuilt from
 * the generated shapes, the way every other contract module is. Until then a
 * reader checks every member of every body, so a body that breaks the contract
 * still fails at the boundary with the name of the field. The status and the
 * grade of a unit are the generated ones already, because the counter routes
 * brought both into the document.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoDate, IsoTimestamp, Money, Schemas } from './contract-kit'

/** Where a unit stands in its lifecycle. The backend's own list. */
type UnitStatus = Schemas['AssetStatus']

/** The grade a unit is in. A is best. */
type UnitGrade = Schemas['ConditionGrade']

/**
 * One unit as the register shows it, retired or not.
 *
 * `allowedTransitions` lists the statuses the owner may move the unit to by
 * hand from where it stands now. The server works it out from the asset
 * lifecycle rules, so the screen offers exactly those moves and holds no copy
 * of the rules. It is empty for a unit no move by hand can change.
 *
 * `activeAllocationCount` is how many bookings hold the unit now, and
 * `openDamageReports` how many of its damage reports are open or in the
 * workshop. `serialNumber`, `hourMeterReading` and `notes` are null when the
 * unit has none, and `retiredOn` is null until the unit is retired. A retired
 * unit keeps its row and its history, because nothing is ever deleted.
 */
export interface AdminAsset {
  id: string
  assetTag: string
  modelId: string
  modelName: string
  modelSlug: string
  categoryName: string
  branchCode: string
  branchName: string
  serialNumber: string | null
  status: UnitStatus
  conditionGrade: UnitGrade
  acquiredOn: IsoDate
  acquisitionCost: Money
  hourMeterReading: number | null
  notes: string | null
  retiredOn: IsoDate | null
  activeAllocationCount: number
  openDamageReports: number
  allowedTransitions: UnitStatus[]
}

/** Where an entry of a unit's history comes from. */
export type AssetHistoryKind = 'ALLOCATION' | 'RENTAL' | 'DAMAGE_REPORT' | 'AUDIT_EVENT'

/**
 * One entry of a unit's history. `summary` is the server's sentence about
 * what happened. `reference` is the booking, the hire or the damage report
 * the entry belongs to, by the reference people quote, or null when it
 * belongs to none.
 */
export interface AssetHistoryEntry {
  at: IsoTimestamp
  kind: AssetHistoryKind
  summary: string
  reference: string | null
}

/**
 * `GET /api/admin/assets/{tag}`. One unit with its history, the newest first,
 * built from its allocations, its hires, its damage reports and its audit
 * events, at most fifty entries. A registration, a change and a move answer
 * with the unit this way too, read once the change has committed.
 */
export interface AdminAssetDetail extends AdminAsset {
  history: AssetHistoryEntry[]
}

/**
 * The query `GET /api/admin/assets` accepts.
 *
 * `q` is free text the server matches against the tag, the serial number and
 * the model name. `branchCode`, `status` and `modelId` each narrow the list to
 * one value. Every filter may be left out. The screen always sends the page
 * and its size.
 */
export interface AdminAssetQuery {
  q?: string
  branchCode?: string
  status?: UnitStatus
  modelId?: string
  page: number
  pageSize: number
}

/** `GET /api/admin/assets`. One page of the units that match, in tag order. */
export interface AdminAssetPage {
  items: AdminAsset[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body `POST /api/admin/assets` accepts. A new unit starts at `INTAKE`.
 * Its tag, model and branch never change afterwards. A tag another unit
 * carries is refused with a 422 naming `assetTag`, and every other refusal
 * names its field too. The screen always sends every field, null for a serial
 * number, a meter reading or notes the unit does not have.
 */
export interface NewAssetRequest {
  assetTag: string
  modelId: string
  branchCode: string
  serialNumber: string | null
  conditionGrade: UnitGrade
  acquiredOn: IsoDate
  acquisitionCost: Money
  hourMeterReading: number | null
  notes: string | null
}

/**
 * The body `PATCH /api/admin/assets/{tag}` accepts. Any of the serial number,
 * the grade, the meter reading and the notes. A field left out keeps its
 * value, and null clears the serial number, the meter reading or the notes.
 * The tag, the model and the branch are not among them, because they never
 * change, and the server refuses each with a 422 naming it.
 */
export interface AssetChangesRequest {
  serialNumber?: string | null
  conditionGrade?: UnitGrade
  hourMeterReading?: number | null
  notes?: string | null
}

/**
 * The body `POST /api/admin/assets/{tag}/transitions` accepts. The status to
 * move the unit to, and why. The reason is required for `RETIRED`,
 * `QUARANTINED` and `UNDER_REPAIR`, and the server refuses a move without one
 * with a 422 naming `reason`. A move the lifecycle does not allow from where
 * the unit stands is a 409 naming that status, and so is a retirement while a
 * booking holds the unit, which names the booking.
 */
export interface AssetTransitionRequest {
  to: UnitStatus
  reason?: string
}
