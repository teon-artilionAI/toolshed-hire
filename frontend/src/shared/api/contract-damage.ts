/**
 * The damage and quarantine wire types.
 *
 * Filing a damage report, listing and reading the reports of a unit, sending a
 * report for repair and resolving it. They are built from the generated schema
 * the way every other wire type is, so a route, a field or a value the backend
 * changes stops the application compiling until it follows. They live apart
 * from contract.ts only to keep each file a size that can be read in one
 * sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  CreatedJsonOf,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

/**
 * How bad the damage is. A write off is a unit not worth repairing. The
 * severity alone retires nothing. Only an owner closing the report as written
 * off does.
 */
export type DamageSeverity = Schemas['DamageSeverity']

/**
 * Where a report stands. It is filed `OPEN`, the owner may send it to
 * `UNDER_REPAIR`, and it is closed as `RESOLVED` or `WRITTEN_OFF`.
 */
export type DamageStatus = Schemas['DamageStatus']

/**
 * The body `POST /api/damage-reports/{id}/resolution` accepts, from an
 * administrator.
 *
 * `actualRepairCost` is required for `RESOLVED`, which puts the unit back on
 * the shelf once it has no other open report. `WRITTEN_OFF` retires the unit
 * and is refused with a 409 while the unit is set aside for a booking (BR-37,
 * BR-38). The generated type lets the cost and the notes be left out, and the
 * screen always sends both, with null for one left empty, so here each is
 * present.
 */
export type ResolveDamageReportRequest = Refine<
  BodyOf<Paths['/api/damage-reports/{id}/resolution']['post']>,
  { actualRepairCost: Money | null; resolutionNotes: string | null }
>

/** The two ways the owner closes a report. */
export type DamageOutcome = ResolveDamageReportRequest['outcome']

/**
 * One damage report, from every damage route. Filing answers 201 with the new
 * report, and the read and the owner's two moves answer 200 with it, so this
 * is built from all four.
 *
 * `rentalId`, `rentalReference` and `rentalItemId` are null for damage found
 * outside a hire. `recoveryCharged` is the VAT inclusive amount a chargeable
 * report raised on the hire, and null when it raised none. `replacementValue`
 * is the most a customer may be charged for the unit, copied onto the booking
 * of the hire, or the model's own value outside a hire. `actualRepairCost`,
 * `resolvedAt` and `resolutionNotes` are null until the report is closed.
 */
export type DamageReport = Refine<
  JsonOf<Paths['/api/damage-reports/{id}']['get']> &
    CreatedJsonOf<Paths['/api/damage-reports']['post']> &
    JsonOf<Paths['/api/damage-reports/{id}/repair']['post']> &
    JsonOf<Paths['/api/damage-reports/{id}/resolution']['post']>,
  {
    repairEstimate: Money
    actualRepairCost: Money | null
    recoveryCharged: Money | null
    replacementValue: Money
    reportedAt: IsoTimestamp
    resolvedAt: IsoTimestamp | null
  }
>

/**
 * The body `POST /api/damage-reports` accepts, from staff at the branch that
 * holds the unit.
 *
 * `chargeableToCustomer` has no default, and a body without it is refused with
 * a 422 (BR-40). `recoveryAmount` is a VAT inclusive amount, written as money
 * is and never as a number. It is required when the customer is charged and a
 * rental item is named, refused when it exceeds the replacement value copied
 * onto the booking (BR-39), and refused when the customer is not charged or
 * there is no hire. A unit that came back damaged waits for the report of that
 * return, and the API refuses a report about it that does not name that rental
 * item with a 409. The generated type lets the rental item and the amount be
 * left out, and the screen always sends every member, with null for what does
 * not apply, so here each is present.
 */
export type FileDamageReportRequest = Refine<
  BodyOf<Paths['/api/damage-reports']['post']>,
  { rentalItemId: string | null; repairEstimate: Money; recoveryAmount: Money | null }
>

/**
 * The query `GET /api/damage-reports` accepts, for staff.
 *
 * Every filter may be left out, and the API reads a null one as left out.
 * `page` counts from 1 and `pageSize` is 1 to 50. The generated type lets the
 * page and its size be left out, and the screen always sends both, so here
 * they are required.
 */
export type DamageReportListQuery = Refine<
  QueryOf<Paths['/api/damage-reports']['get']>,
  { page: number; pageSize: number }
>

/** `GET /api/damage-reports`. Newest first. */
export type DamageReportPage = Refine<JsonOf<Paths['/api/damage-reports']['get']>, { items: DamageReport[] }>
