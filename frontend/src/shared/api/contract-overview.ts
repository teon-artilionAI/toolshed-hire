/**
 * The counter overview wire types.
 *
 * The dashboard, the diary, the no show and the asset locator. They are built
 * from the generated schema the way every other wire type is, so a route, a
 * field or a value the backend changes stops the application compiling until
 * it follows. They live apart from contract.ts only to keep each file a size
 * that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { BodyOf, IsoDate, JsonOf, Money, Paths, QueryOf, Refine, Schemas } from './contract-kit'

type ReservationStatus = Schemas['ReservationStatus']

/**
 * The query `GET /api/counter/dashboard` accepts.
 *
 * Counter staff may leave the branch out and get their own, and are refused a
 * 403 for naming another. An administrator must name one. The generated type
 * lets it be left out, and the screens always send the branch the person
 * works at, which for counter staff is their own, so here it is required.
 */
export type DashboardQuery = Refine<QueryOf<Paths['/api/counter/dashboard']['get']>, { branchCode: string }>

/** How many of each thing there is today. These are the true totals, even
 *  where a list below them is cut short. */
export type DashboardCounts = Schemas['DashboardCountsResponse']

/**
 * A booking due to be collected today.
 *
 * `summary` is what is on it in a few words, for example "2 x Bosch GBH 2-26",
 * written by the server.
 */
export type DashboardCollection = Refine<Schemas['CollectionDueResponse'], { from: IsoDate; to: IsoDate }>

/** A hire due back today. `itemsOut` of its `itemCount` units are still out. */
export type DashboardReturn = Refine<Schemas['ReturnDueResponse'], { dueBackOn: IsoDate }>

/**
 * A hire past the day it was due back.
 *
 * `daysOverdue` and `lateFeeAccrued` are the server's. The late fee is a VAT
 * inclusive amount, and the browser never works one out.
 */
export type DashboardOverdue = Refine<
  Schemas['OverdueRentalResponse'],
  { dueBackOn: IsoDate; lateFeeAccrued: Money }
>

/**
 * `GET /api/counter/dashboard`. What is due today at one branch.
 *
 * `date` is today at the branch, as the server sees it. Each list holds at most
 * 50 rows and the counts are the true totals, so a list can be shorter than
 * its count.
 */
export type CounterDashboard = Refine<
  JsonOf<Paths['/api/counter/dashboard']['get']>,
  {
    date: IsoDate
    collectionsDue: DashboardCollection[]
    returnsDue: DashboardReturn[]
    overdue: DashboardOverdue[]
  }
>

/**
 * The query `GET /api/counter/diary` accepts.
 *
 * `from` is the first day and defaults to today. `days` is 1 to 7 and defaults
 * to 1. The branch follows the same rule as the dashboard. The generated type
 * lets all three be left out, and the screens always send all three, so here
 * each is required.
 */
export type DiaryQuery = Refine<
  QueryOf<Paths['/api/counter/diary']['get']>,
  { branchCode: string; from: IsoDate; days: number }
>

/**
 * The statuses a booking in the diary can be in. A booking that never got as
 * far as confirmed, or was cancelled, is not in the diary.
 *
 * The generated type allows every status a reservation has, because the
 * backend sends the one enumeration. The diary only ever lists these four, and
 * the reader checks that it does.
 */
export type DiaryCollectionStatus = Extract<ReservationStatus, 'CONFIRMED' | 'COLLECTED' | 'RETURNED' | 'NO_SHOW'>

/**
 * A booking that starts on a day of the diary.
 *
 * `canMarkNoShow` is the server's answer for the person asking, at the moment
 * they asked. A screen offers the no show from it and from nothing else.
 *
 * It carries no key of the hire a collected booking became, so a screen
 * reaches that hire through the checkout of the booking.
 */
export type DiaryCollection = Refine<
  Schemas['DiaryCollectionResponse'],
  { status: DiaryCollectionStatus; from: IsoDate; to: IsoDate }
>

/** A hire due back on a day of the diary. */
export type DiaryReturn = Refine<Schemas['DiaryReturnResponse'], { dueBackOn: IsoDate }>

/** One day of the diary, with what goes out and what comes back. */
export type DiaryDay = Refine<
  Schemas['DiaryDayResponse'],
  { date: IsoDate; collections: DiaryCollection[]; returns: DiaryReturn[] }
>

/** `GET /api/counter/diary`. One day, or up to seven in a row. */
export type BranchDiary = Refine<JsonOf<Paths['/api/counter/diary']['get']>, { days: DiaryDay[] }>

/** The body `POST /api/reservations/{id}/no-show` accepts. The reason is
 *  required and is at most 200 characters once the spaces around it are gone. */
export type NoShowRequest = BodyOf<Paths['/api/reservations/{id}/no-show']['post']>

/**
 * Where a unit stands. The backend's own list, which has no reserved state,
 * because a unit set aside for a booking is known from its allocation.
 */
export type AssetStatus = Schemas['AssetStatus']

/**
 * The query `GET /api/assets/locator` accepts.
 *
 * `q` is required and is two to eighty characters once the spaces around it
 * are gone. It is matched against the asset tag and the model name.
 * `pageSize` is 1 to 50. The generated type lets the page and its size be left
 * out, and the screen always sends both, so here they are required.
 */
export type LocatorQuery = Refine<
  QueryOf<Paths['/api/assets/locator']['get']>,
  { page: number; pageSize: number }
>

/**
 * One unit the locator found, at any branch.
 *
 * `dueBackOn` and `rentalReference` are set only while the unit is on hire,
 * and are null otherwise.
 */
export type LocatedUnit = Refine<Schemas['AssetLocationResponse'], { dueBackOn: IsoDate | null }>

/** `GET /api/assets/locator`. In tag order. */
export type LocatorPage = Refine<JsonOf<Paths['/api/assets/locator']['get']>, { items: LocatedUnit[] }>
