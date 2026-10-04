/**
 * The asset register wire types. Every unit of the fleet as the owner keeps
 * it, retired or not, with its paperwork, where it stands in its lifecycle,
 * the moves it may make by hand and its history.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * The generated types say less than the server does in two ways, and the
 * types below say it exactly. The generated body of an edit lets the grade be
 * null, and the server refuses null there naming `conditionGrade`, because
 * every unit has a grade. So here the grade of an edit is a value or left out.
 * And the generated query and registration let some members be left out that
 * the screen always sends, so here those are required.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type {
  BodyOf,
  CreatedJsonOf,
  IsoDate,
  IsoTimestamp,
  JsonOf,
  Money,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

type AssetsRoute = Paths['/api/admin/assets']
type AssetRoute = Paths['/api/admin/assets/{tag}']
type TransitionsRoute = Paths['/api/admin/assets/{tag}/transitions']

/** The members of a unit the document can only call a `string`, by the names
 *  of what they hold. */
interface UnitValues {
  acquiredOn: IsoDate
  acquisitionCost: Money
  retiredOn: IsoDate | null
}

/**
 * One unit as the register shows it, retired or not.
 *
 * `allowedTransitions` lists the statuses the owner may move the unit to by
 * hand from where it stands now. The server works it out from the asset
 * lifecycle rules, so the screen offers exactly those moves and holds no copy
 * of the rules. It is empty for a unit on hire, which only its return or its
 * loss can move. A move it lists can still be refused for what holds the unit
 * at that moment, a booking for a retirement and an open damage report for a
 * move back to the shelf.
 *
 * `activeAllocationCount` is how many bookings hold the unit now, and
 * `openDamageReports` how many of its damage reports are open or in the
 * workshop. `serialNumber`, `hourMeterReading` and `notes` are null when the
 * unit has none, and `retiredOn` is null until the unit is retired. A retired
 * unit keeps its row and its history, because nothing is ever deleted.
 */
export type AdminAsset = Refine<JsonOf<AssetsRoute['get']>['items'][number], UnitValues>

/** Where an entry of a unit's history comes from. */
export type AssetHistoryKind = Schemas['AssetHistoryKind']

/**
 * One entry of a unit's history. `summary` is the server's sentence about
 * what happened, with the reason beside a move that was given one.
 * `reference` is the booking, the hire or the damage report the entry belongs
 * to, by the reference people quote, or null when it belongs to none.
 */
export type AssetHistoryEntry = Refine<JsonOf<AssetRoute['get']>['history'][number], { at: IsoTimestamp }>

/**
 * `GET /api/admin/assets/{tag}`. One unit with its history, the newest first,
 * built from its allocations, its hires, its damage reports and its audit
 * events, at most fifty entries. A registration, a change and a move answer
 * with the unit this way too, read once the change has committed, so it is
 * built from all four.
 */
export type AdminAssetDetail = Refine<
  JsonOf<AssetRoute['get']> &
    CreatedJsonOf<AssetsRoute['post']> &
    JsonOf<AssetRoute['patch']> &
    JsonOf<TransitionsRoute['post']>,
  UnitValues & { history: AssetHistoryEntry[] }
>

/**
 * The query `GET /api/admin/assets` accepts.
 *
 * `q` is free text of two to eighty characters, which the server matches
 * against the tag, the serial number and the model name. `branchCode`,
 * `status` and `modelId` each narrow the list to one value. Every filter may
 * be left out. The generated type lets the page and its size be left out, and
 * the screen always sends both, so here they are required.
 */
export type AdminAssetQuery = Refine<QueryOf<AssetsRoute['get']>, { page: number; pageSize: number }>

/** `GET /api/admin/assets`. One page of the units that match, in tag order. */
export type AdminAssetPage = Refine<JsonOf<AssetsRoute['get']>, { items: AdminAsset[] }>

/**
 * The body `POST /api/admin/assets` accepts. A new unit starts at `INTAKE`.
 * Its tag, model and branch never change afterwards. A tag another unit
 * carries, a cost below zero, a day after today and an unknown model or
 * branch are each refused with a 422 naming the field. The generated type
 * lets the serial number, the meter reading and the notes be left out, and
 * the screen always sends all three, null for none, so here they are required.
 */
export type NewAssetRequest = Refine<
  BodyOf<AssetsRoute['post']>,
  {
    serialNumber: string | null
    acquiredOn: IsoDate
    acquisitionCost: Money
    hourMeterReading: number | null
    notes: string | null
  }
>

/**
 * The body `PATCH /api/admin/assets/{tag}` accepts. Any of the serial number,
 * the grade, the meter reading and the notes. A field left out keeps its
 * value, and null clears the serial number, the meter reading or the notes.
 * The grade cannot be cleared. The tag, the model and the branch are not
 * among them, because they never change, and the server refuses a body that
 * names one.
 */
export type AssetChangesRequest = Refine<
  BodyOf<AssetRoute['patch']>,
  { conditionGrade?: Schemas['ConditionGrade'] }
>

/**
 * The body `POST /api/admin/assets/{tag}/transitions` accepts. The status to
 * move the unit to, and why.
 *
 * The reason is required for `RETIRED`, `QUARANTINED` and `UNDER_REPAIR`, five
 * to two hundred characters once trimmed, and the server refuses a move
 * without one with a 422 naming `reason`. `ON_HIRE` and `LOST` are refused
 * with a 422 naming `to`, because only checkout and the loss route set them. A
 * move the lifecycle does not allow from where the unit stands is a 409, and
 * so is a retirement while a booking holds the unit, which names the booking,
 * and a move back to the shelf while a damage report on it is open, which
 * names the report.
 */
export type AssetTransitionRequest = BodyOf<TransitionsRoute['post']>
