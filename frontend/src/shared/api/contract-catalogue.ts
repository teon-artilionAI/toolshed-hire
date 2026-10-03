/**
 * The catalogue wire types.
 *
 * The branches, the categories, the models, the availability searches and the
 * quote. They are built from the generated schema the way every other wire
 * type is, so a route, a field or a value the backend changes stops the
 * application compiling until it follows. They live apart from contract.ts
 * only to keep each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { ClockTime, IsoDate, JsonOf, Money, Paths, QueryOf, Refine, Schemas } from './contract-kit'

/** One trading branch. The codes in use are CBD, BLV and SMW. */
export type Branch = Refine<Schemas['BranchResponse'], { opensAt: ClockTime; closesAt: ClockTime }>

/** `GET /api/branches`. */
export type BranchList = Refine<JsonOf<Paths['/api/branches']['get']>, { items: Branch[] }>

/**
 * One catalogue category. `parentCode` is null for a top level category.
 *
 * `modelCount` on a parent includes the models of its children. `description`
 * is an empty string when the category has none.
 */
export type Category = Schemas['CategoryResponse']

/** `GET /api/catalogue/categories`. Each parent arrives before its children. */
export type CategoryList = JsonOf<Paths['/api/catalogue/categories']['get']>

/** The orders a model list can be asked for. */
export type ModelSort = Schemas['ModelSortParameter']

/** A catalogue entry as it appears in a list. `imagePath` is null when the
 *  model has no photograph. */
export type ModelSummary = Refine<
  Schemas['ModelSummaryResponse'],
  { dailyRate: Money; weeklyRate: Money; depositAmount: Money }
>

/** `GET /api/catalogue/models/{slug}`. */
export type ModelDetail = Refine<
  JsonOf<Paths['/api/catalogue/models/{slug}']['get']>,
  { dailyRate: Money; weeklyRate: Money; depositAmount: Money; lateFeePerDay: Money }
>

/**
 * The query `GET /api/catalogue/models` accepts.
 *
 * `category` is a category slug, and a parent category includes its children.
 * `q` is two characters or more. `page` counts from 1. `pageSize` is 1 to 50,
 * and the API uses 24 when it is left out.
 */
export type ModelListQuery = QueryOf<Paths['/api/catalogue/models']['get']>

/** `GET /api/catalogue/models`. */
export type ModelPage = Refine<
  JsonOf<Paths['/api/catalogue/models']['get']>,
  { items: ModelSummary[] }
>

/** Whether one branch can supply a model for the whole period asked about. */
export type BranchAvailability = Schemas['BranchAvailabilityResponse']

/** One model in an availability search, with an answer from every branch. */
export type ModelAvailabilityRow = Refine<
  Schemas['ModelAvailabilityRowResponse'],
  { model: ModelSummary }
>

/**
 * The query `GET /api/catalogue/availability` accepts.
 *
 * `to` is the return day and is exclusive. `branch` does more than pick a
 * column. With it, the list holds only the models that are free at that
 * branch. This route refuses a period longer than 28 days and does not apply
 * the hire limits of each model. The single model route applies those.
 */
export type AvailabilityQuery = Refine<
  QueryOf<Paths['/api/catalogue/availability']['get']>,
  { from: IsoDate; to: IsoDate }
>

/** `GET /api/catalogue/availability`. */
export type AvailabilityPage = Refine<
  JsonOf<Paths['/api/catalogue/availability']['get']>,
  { from: IsoDate; to: IsoDate; items: ModelAvailabilityRow[] }
>

/**
 * The query `GET /api/catalogue/models/{slug}/availability` accepts.
 *
 * `quantity` is 1 to 10, and the API uses 1 when it is left out. This route
 * also applies the shortest and longest hire of the model itself.
 */
export type ModelAvailabilityQuery = Refine<
  QueryOf<Paths['/api/catalogue/models/{slug}/availability']['get']>,
  { from: IsoDate; to: IsoDate }
>

/** `GET /api/catalogue/models/{slug}/availability`. */
export type ModelAvailability = Refine<
  JsonOf<Paths['/api/catalogue/models/{slug}/availability']['get']>,
  { from: IsoDate; to: IsoDate }
>

/** Which of the two ways of charging one unit came out cheaper. */
export type QuoteBasis = Schemas['QuoteBasis']

/**
 * What one unit costs for the period, before VAT, and how that was reached.
 *
 * `basis` is `weekly` when the whole weeks at the weekly rate plus the days
 * left over at the daily rate cost less than every day at the daily rate. It
 * is `daily` otherwise, and then every one of the hire days is a daily one.
 */
export type UnitQuote = Refine<
  Schemas['UnitQuoteResponse'],
  { dailyRate: Money; weeklyRate: Money; amountExVat: Money }
>

/**
 * The query `GET /api/catalogue/models/{slug}/quote` accepts.
 *
 * `to` is the return day and is exclusive. `quantity` is 1 to 10, and the API
 * uses 1 when it is left out.
 */
export type ModelQuoteQuery = Refine<
  QueryOf<Paths['/api/catalogue/models/{slug}/quote']['get']>,
  { from: IsoDate; to: IsoDate }
>

/**
 * `GET /api/catalogue/models/{slug}/quote`. What a hire will cost.
 *
 * Every figure is the server's. `totalIncVat` is the hire charge. The deposit
 * is not part of it, because a deposit is held and returned and not charged.
 * The VAT is worked out on the subtotal after the discount. The two
 * percentages are strings with two decimals like the money, for example
 * "15.00".
 */
export type ModelQuote = Refine<
  JsonOf<Paths['/api/catalogue/models/{slug}/quote']['get']>,
  {
    from: IsoDate
    to: IsoDate
    perUnit: UnitQuote
    subtotalExVat: Money
    discountAmount: Money
    vatAmount: Money
    totalIncVat: Money
    depositPerUnit: Money
    depositTotal: Money
    lateFeePerDay: Money
  }
>
