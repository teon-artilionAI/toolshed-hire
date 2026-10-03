/**
 * The damage and quarantine wire types.
 *
 * Filing a damage report, listing and reading the reports of a unit, sending a
 * report for repair and resolving it. Unlike every other contract module these
 * are written by hand. The OpenAPI document the backend commits does not
 * describe the damage routes yet, so schema.d.ts has nothing to build them
 * from. I wrote each one from the agreed contract for the change that adds the
 * routes, with the same names, members and values, and in the same style as
 * the generated types. Once the document has the routes, each type here should
 * be rebuilt from the generated file like the rest, and anything the backend
 * named differently then stops compiling.
 *
 * The severities are not listed in that contract. They are the ones the
 * database stores, `MINOR`, `MAJOR` and `WRITE_OFF`.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoTimestamp, Money } from './contract-kit'

/** How bad the damage is. A write off is a unit not worth repairing. */
export type DamageSeverity = 'MINOR' | 'MAJOR' | 'WRITE_OFF'

/**
 * Where a report stands. It is filed `OPEN`, the owner may send it to
 * `UNDER_REPAIR`, and it is closed as `RESOLVED` or `WRITTEN_OFF`.
 */
export type DamageStatus = 'OPEN' | 'UNDER_REPAIR' | 'RESOLVED' | 'WRITTEN_OFF'

/** The two ways the owner closes a report. */
export type DamageOutcome = Extract<DamageStatus, 'RESOLVED' | 'WRITTEN_OFF'>

/**
 * One damage report, from every damage route.
 *
 * `rentalId`, `rentalReference` and `rentalItemId` are null for damage found
 * outside a hire. `recoveryCharged` is the VAT inclusive amount a chargeable
 * report raised on the hire, and null when it raised none. `replacementValue`
 * is the most a customer may be charged for the unit, copied onto the booking
 * of the hire, or the model's own value outside a hire. `actualRepairCost`,
 * `resolvedAt` and `resolutionNotes` are null until the report is closed.
 */
export interface DamageReport {
  id: string
  reference: string
  assetTag: string
  modelName: string
  branchCode: string
  rentalId: string | null
  rentalReference: string | null
  rentalItemId: string | null
  severity: DamageSeverity
  status: DamageStatus
  description: string
  repairEstimate: Money
  actualRepairCost: Money | null
  chargeableToCustomer: boolean
  recoveryCharged: Money | null
  replacementValue: Money
  reportedAt: IsoTimestamp
  reportedByName: string
  resolvedAt: IsoTimestamp | null
  resolutionNotes: string | null
}

/**
 * The body `POST /api/damage-reports` accepts, from staff at the branch that
 * holds the unit.
 *
 * `chargeableToCustomer` has no default, and a body without it is refused with
 * a 422 (BR-40). `recoveryAmount` is a VAT inclusive amount. It is required
 * when the customer is charged and a rental item is named, refused when it
 * exceeds the replacement value copied onto the booking (BR-39), and refused
 * when the customer is not charged or there is no hire. The screen always
 * sends every member, with null for what does not apply.
 */
export interface FileDamageReportRequest {
  assetTag: string
  rentalItemId: string | null
  severity: DamageSeverity
  description: string
  repairEstimate: Money
  chargeableToCustomer: boolean
  recoveryAmount: Money | null
}

/**
 * The query `GET /api/damage-reports` accepts, for staff.
 *
 * Every filter may be left out. `page` counts from 1 and `pageSize` is 1 to
 * 50. The screen always sends both.
 */
export interface DamageReportListQuery {
  assetTag?: string
  status?: DamageStatus
  branchCode?: string
  page: number
  pageSize: number
}

/** `GET /api/damage-reports`. Newest first. */
export interface DamageReportPage {
  items: DamageReport[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body `POST /api/damage-reports/{id}/resolution` accepts, from an
 * administrator.
 *
 * `actualRepairCost` is required for `RESOLVED`, which puts the unit back on
 * the shelf once it has no other open report. `WRITTEN_OFF` retires the unit
 * and is refused with a 409 while the unit is set aside for a booking (BR-37,
 * BR-38). The screen sends null for a cost or notes left empty.
 */
export interface ResolveDamageReportRequest {
  outcome: DamageOutcome
  actualRepairCost: Money | null
  resolutionNotes: string | null
}
