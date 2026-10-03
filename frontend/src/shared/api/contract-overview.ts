/**
 * The counter overview wire types, written by hand for now.
 *
 * The dashboard, the diary, the no show and the asset locator. The backend
 * adds these routes in the same change, so the OpenAPI document does not
 * describe them yet and there is nothing to generate them from. I wrote them
 * from the agreed contract, member for member, and the reader beside each
 * route checks every one of them at the boundary. When the document describes
 * the routes, these are built from schema.d.ts like every other wire type and
 * the screens do not change.
 *
 * The statuses a reservation, a hire and a unit's grade can take already come
 * from the generated schema, so I take those from there.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoDate, Money, Schemas } from './contract-kit'

type ReservationStatus = Schemas['ReservationStatus']
type RentalStatus = Schemas['RentalStatus']
type ConditionGrade = Schemas['ConditionGrade']

/**
 * The query `GET /api/counter/dashboard` accepts.
 *
 * Counter staff get their own branch and are refused a 403 for naming
 * another. An administrator must name one. The screens always send the branch
 * the person works at, which for counter staff is their own.
 */
export type DashboardQuery = { branchCode: string }

/** How many of each thing there is today. These are the true totals, even
 *  where a list below them is cut short. */
export type DashboardCounts = {
  collectionsDue: number
  returnsDue: number
  overdue: number
  onHire: number
  quarantined: number
}

/**
 * A booking due to be collected today.
 *
 * `summary` is what is on it in a few words, for example "2 x Bosch GBH 2-26",
 * written by the server.
 */
export type DashboardCollection = {
  reservationId: string
  reference: string
  customerName: string
  customerPhone: string
  from: IsoDate
  to: IsoDate
  unitCount: number
  summary: string
}

/** A hire due back today. `itemsOut` of its `itemCount` units are still out. */
export type DashboardReturn = {
  rentalId: string
  reference: string
  customerName: string
  customerPhone: string
  dueBackOn: IsoDate
  itemsOut: number
  itemCount: number
  summary: string
}

/**
 * A hire past the day it was due back.
 *
 * `daysOverdue` and `lateFeeAccrued` are the server's. The late fee is a VAT
 * inclusive amount, and the browser never works one out.
 */
export type DashboardOverdue = {
  rentalId: string
  reference: string
  customerName: string
  customerPhone: string
  dueBackOn: IsoDate
  daysOverdue: number
  itemsOut: number
  lateFeeAccrued: Money
}

/**
 * `GET /api/counter/dashboard`. What is due today at one branch.
 *
 * `date` is today at the branch, as the server sees it. Each list holds at most
 * 50 rows and the counts are the true totals, so a list can be shorter than
 * its count.
 */
export type CounterDashboard = {
  branchCode: string
  branchName: string
  date: IsoDate
  counts: DashboardCounts
  collectionsDue: DashboardCollection[]
  returnsDue: DashboardReturn[]
  overdue: DashboardOverdue[]
}

/**
 * The query `GET /api/counter/diary` accepts.
 *
 * `from` is the first day and defaults to today. `days` is 1 to 7 and defaults
 * to 1. The branch follows the same rule as the dashboard.
 */
export type DiaryQuery = { branchCode: string; from: IsoDate; days: number }

/** The statuses a booking in the diary can be in. A booking that never got as
 *  far as confirmed, or was cancelled, is not in the diary. */
export type DiaryCollectionStatus = Extract<ReservationStatus, 'CONFIRMED' | 'COLLECTED' | 'RETURNED' | 'NO_SHOW'>

/**
 * A booking that starts on a day of the diary.
 *
 * `canMarkNoShow` is the server's answer for the person asking, at the moment
 * they asked. A screen offers the no show from it and from nothing else.
 */
export type DiaryCollection = {
  reservationId: string
  reference: string
  status: DiaryCollectionStatus
  customerName: string
  customerPhone: string
  from: IsoDate
  to: IsoDate
  unitCount: number
  summary: string
  canMarkNoShow: boolean
}

/** A hire due back on a day of the diary. */
export type DiaryReturn = {
  rentalId: string
  reference: string
  status: RentalStatus
  customerName: string
  customerPhone: string
  dueBackOn: IsoDate
  itemsOut: number
  itemCount: number
  summary: string
}

/** One day of the diary, with what goes out and what comes back. */
export type DiaryDay = {
  date: IsoDate
  collections: DiaryCollection[]
  returns: DiaryReturn[]
}

/** `GET /api/counter/diary`. One day, or up to seven in a row. */
export type BranchDiary = {
  branchCode: string
  branchName: string
  days: DiaryDay[]
}

/** The body `POST /api/reservations/{id}/no-show` accepts. The reason is
 *  required and is at most 200 characters. */
export type NoShowRequest = { reason: string }

/**
 * Where a unit stands. The backend's own list, which has no reserved state,
 * because a unit set aside for a booking is known from its allocation.
 */
export type AssetStatus = 'INTAKE' | 'AVAILABLE' | 'ON_HIRE' | 'QUARANTINED' | 'UNDER_REPAIR' | 'LOST' | 'RETIRED'

/**
 * The query `GET /api/assets/locator` accepts.
 *
 * `q` is required and is two to eighty characters. It is matched against the
 * asset tag and the model name. `pageSize` is 1 to 50.
 */
export type LocatorQuery = { q: string; page: number; pageSize: number }

/**
 * One unit the locator found, at any branch.
 *
 * `dueBackOn` and `rentalReference` are set only while the unit is on hire,
 * and are null otherwise.
 */
export type LocatedUnit = {
  assetTag: string
  modelName: string
  modelSlug: string
  categoryName: string
  branchCode: string
  branchName: string
  status: AssetStatus
  conditionGrade: ConditionGrade
  dueBackOn: IsoDate | null
  rentalReference: string | null
}

/** `GET /api/assets/locator`. */
export type LocatorPage = {
  items: LocatedUnit[]
  page: number
  pageSize: number
  total: number
}
