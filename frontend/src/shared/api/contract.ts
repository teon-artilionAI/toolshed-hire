/**
 * The wire types, all of them, in one place.
 *
 * Every type that mirrors a body the API sends or a query it accepts is
 * exported from here and from nowhere else. The shapes are not written by
 * hand. They come from schema.d.ts, which `npm run api:types` generates from
 * the OpenAPI document the backend commits. When the backend changes a route,
 * a field or a query parameter, the generated file changes with it, and
 * whatever in the application no longer fits stops compiling.
 *
 * Nothing else imports schema.d.ts. Its names follow the backend's class and
 * function names, and a screen should not have to know those.
 *
 * Where the generated type says less than the screens rely on, I keep a more
 * precise type here and say why beside it. A refinement can only name a member
 * the generated type has, and can only narrow it. So a member the backend
 * renames, removes or retypes is still a compile error here.
 *
 * This file holds types only. A runtime value such as a page size limit lives
 * beside the endpoint that uses it, because generated types carry no values.
 */

import type { components, paths } from './schema'

type Schemas = components['schemas']

/** The JSON body of the 200 answer of one operation. An operation that has
 *  lost its 200 answer does not satisfy the constraint and stops compiling. */
type JsonOf<Operation extends { responses: { 200: { content: { 'application/json': unknown } } } }> =
  Operation['responses'][200]['content']['application/json']

/** The JSON body one operation accepts. */
type BodyOf<Operation extends { requestBody: { content: { 'application/json': unknown } } }> =
  Operation['requestBody']['content']['application/json']

/** The query one operation accepts. */
type QueryOf<Operation extends { parameters: { query?: object } }> = NonNullable<
  Operation['parameters']['query']
>

/** Writes an intersection out as one plain object type, so an editor shows the
 *  members and not the arithmetic that produced them. */
type Simplify<Shape> = { [Name in keyof Shape]: Shape[Name] }

/**
 * A generated type with some members replaced by more precise ones.
 *
 * The constraint is what keeps this honest. Each member of `Precise` must
 * exist on `Wire` and must be assignable to what `Wire` says it is.
 */
type Refine<
  Wire,
  Precise extends { [Name in keyof Precise]: Name extends keyof Wire ? Wire[Name] : never },
> = Simplify<Omit<Wire, keyof Precise> & Precise>

/**
 * An amount in rand as the API writes it, for example "280.00".
 *
 * The generated type is a plain `string`, because the document cannot say
 * "two decimals". I keep the name so a money member reads as money. It stays a
 * string all the way to the screen, so no float ever gets a chance to change
 * the figure a customer is shown. `readMoney` checks the two decimals.
 */
export type Money = string

/** A calendar date as the API writes it, `YYYY-MM-DD`. Generated as `string`. */
export type IsoDate = string

/** A time of day as the API writes it, `HH:MM`. Generated as `string`. */
export type ClockTime = string

/**
 * An RFC 9457 problem document, as the backend's `ProblemDetail` emits it.
 *
 * The API may send null for the three optional members. The client leaves a
 * null one out when it reads the document, so here each is present or absent
 * and never null.
 *
 * `errors` says more about the refusal. On a 422 it holds one member,
 * `fields`, and that holds a sentence for each refused value. Each name there
 * starts with where the value came from, for example `query.to` or
 * `body.email`. On a 404 it names what was looked for. problem-fields.ts turns
 * the 422 shape into a lookup by the bare field name.
 */
export type ProblemDocument = Refine<
  Schemas['ProblemDetail'],
  {
    instance?: string
    errors?: Record<string, unknown>
    /** The same value as the `X-Request-ID` response header. */
    requestId?: string
  }
>

/** The roles the backend maps its stored roles onto. The generated type is a
 *  plain `string`, and the screens branch on the role, so I keep the union. */
export type UserRole = 'customer' | 'counter' | 'admin'

/** What `GET /api/health` reports about its own dependencies. */
export type HealthReport = JsonOf<paths['/api/health']['get']>

/**
 * The signed in account. `GET /api/me`, and the `user` member of what login
 * and refresh answer with.
 *
 * Counter staff carry the code of the branch they work at. Customers and
 * administrators do not, and `branchCode` is null for them. Null is a fact
 * about the role and not missing data. The generated type also lets the member
 * be left out. The reader in auth.ts turns a missing one into null, so here it
 * is always present.
 */
export type SessionUser = Refine<
  JsonOf<paths['/api/me']['get']>,
  { role: UserRole; branchCode: string | null }
>

/** The body `POST /api/auth/login` accepts. */
export type LoginRequest = BodyOf<paths['/api/auth/login']['post']>

/** The one token type the API issues. The generated type is a plain `string`,
 *  and the client only knows how to send this one. */
export type AccessTokenType = 'Bearer'

/**
 * What `POST /api/auth/login` and `POST /api/auth/refresh` both answer with.
 *
 * The access token, how many seconds it lasts, and whom it belongs to. The
 * refresh token is not here. The server keeps it in an HttpOnly cookie that
 * the page cannot read.
 *
 * `POST /api/auth/logout` takes no body and answers 204 with none, so it needs
 * no type here.
 */
export type SessionGrant = Refine<
  JsonOf<paths['/api/auth/login']['post']> & JsonOf<paths['/api/auth/refresh']['post']>,
  { tokenType: AccessTokenType; user: SessionUser }
>

/** One trading branch. The codes in use are CBD, BLV and SMW. */
export type Branch = Refine<Schemas['BranchResponse'], { opensAt: ClockTime; closesAt: ClockTime }>

/** `GET /api/branches`. */
export type BranchList = Refine<JsonOf<paths['/api/branches']['get']>, { items: Branch[] }>

/**
 * One catalogue category. `parentCode` is null for a top level category.
 *
 * `modelCount` on a parent includes the models of its children. `description`
 * is an empty string when the category has none.
 */
export type Category = Schemas['CategoryResponse']

/** `GET /api/catalogue/categories`. Each parent arrives before its children. */
export type CategoryList = JsonOf<paths['/api/catalogue/categories']['get']>

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
  JsonOf<paths['/api/catalogue/models/{slug}']['get']>,
  { dailyRate: Money; weeklyRate: Money; depositAmount: Money; lateFeePerDay: Money }
>

/**
 * The query `GET /api/catalogue/models` accepts.
 *
 * `category` is a category slug, and a parent category includes its children.
 * `q` is two characters or more. `page` counts from 1. `pageSize` is 1 to 50,
 * and the API uses 24 when it is left out.
 */
export type ModelListQuery = QueryOf<paths['/api/catalogue/models']['get']>

/** `GET /api/catalogue/models`. */
export type ModelPage = Refine<
  JsonOf<paths['/api/catalogue/models']['get']>,
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
  QueryOf<paths['/api/catalogue/availability']['get']>,
  { from: IsoDate; to: IsoDate }
>

/** `GET /api/catalogue/availability`. */
export type AvailabilityPage = Refine<
  JsonOf<paths['/api/catalogue/availability']['get']>,
  { from: IsoDate; to: IsoDate; items: ModelAvailabilityRow[] }
>

/**
 * The query `GET /api/catalogue/models/{slug}/availability` accepts.
 *
 * `quantity` is 1 to 10, and the API uses 1 when it is left out. This route
 * also applies the shortest and longest hire of the model itself.
 */
export type ModelAvailabilityQuery = Refine<
  QueryOf<paths['/api/catalogue/models/{slug}/availability']['get']>,
  { from: IsoDate; to: IsoDate }
>

/** `GET /api/catalogue/models/{slug}/availability`. */
export type ModelAvailability = Refine<
  JsonOf<paths['/api/catalogue/models/{slug}/availability']['get']>,
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
  QueryOf<paths['/api/catalogue/models/{slug}/quote']['get']>,
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
  JsonOf<paths['/api/catalogue/models/{slug}/quote']['get']>,
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
