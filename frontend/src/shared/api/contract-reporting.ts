/**
 * The reporting wire types. The utilisation and gross contribution report, its
 * CSV, and the owner's dashboard.
 *
 * These are written by hand from the agreed contract for the reporting routes,
 * because the OpenAPI document the backend commits does not describe them yet.
 * Once it does, each one is replaced by a type built from the generated schema
 * the way the other contract modules build theirs, and the readers in
 * reporting.ts and admin-dashboard.ts stay as they are.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoDate, Money } from './contract-kit'
import type { AssetStatus } from './contract-overview'

/**
 * A percentage as the API writes it, a string with two decimals such as
 * "15.78". It stays a string all the way to the screen, like money.
 */
export type Percent = string

/** The levels the report can be grouped at. `asset` is one row per unit. */
export type ReportGrouping = 'asset' | 'model' | 'category' | 'branch'

/**
 * The query `GET /api/admin/reports/utilisation` accepts.
 *
 * `from` and `to` are required, and `to` is not counted, so the period is
 * `[from, to)`. The server refuses a `to` that is not after `from` and a period
 * longer than 366 days, with a 422 naming the field. The two filters are
 * optional. The screens always send the grouping, the page and its size.
 */
export interface UtilisationReportQuery {
  from: IsoDate
  to: IsoDate
  groupBy: ReportGrouping
  branchCode?: string
  categorySlug?: string
  page: number
  pageSize: number
}

/** The query of the CSV route. The same as the report's, with every row and no page. */
export type UtilisationCsvQuery = Omit<UtilisationReportQuery, 'page' | 'pageSize'>

/** The two definitions, in the server's own words. A screen shows them in full. */
export interface ReportDefinitions {
  utilisation: string
  grossContribution: string
}

/**
 * The figures of one row, or of the whole report.
 *
 * `utilisationPercent` is null when there were no serviceable days. Gross
 * contribution is the revenue less the repair costs, so it can run below
 * zero, and it is never profit. The other amounts are sums of charges and are
 * read as able to run below zero as well. Every figure is the server's, and
 * the browser adds none of them up.
 */
export interface ReportFigures {
  assetCount: number
  daysOnHire: number
  serviceableDays: number
  utilisationPercent: Percent | null
  hireRevenueExVat: Money
  lateFeesExVat: Money
  damageRecoveryExVat: Money
  repairCosts: Money
  grossContribution: Money
}

/**
 * One row of the report.
 *
 * `key` and `label` say what the row is at its grouping. The other four name
 * where it sits, and each is null where it does not apply, for example
 * `assetTag` on a row for a model. Only a row for one unit carries `status`,
 * and it is null on every other row.
 */
export interface ReportRow extends ReportFigures {
  key: string
  label: string
  branchCode: string | null
  categoryName: string | null
  modelName: string | null
  assetTag: string | null
  status: AssetStatus | null
}

/**
 * `GET /api/admin/reports/utilisation`. One page of rows, highest gross
 * contribution first, with the totals over every row and not only the page.
 */
export interface UtilisationReport {
  from: IsoDate
  to: IsoDate
  groupBy: ReportGrouping
  definitions: ReportDefinitions
  totals: ReportFigures
  items: ReportRow[]
  page: number
  pageSize: number
  total: number
}

/** What is due and where the fleet stands at one branch today. */
export interface FleetCounts {
  collectionsDue: number
  returnsDue: number
  overdue: number
  onHire: number
  quarantined: number
  underRepair: number
  available: number
}

/** One branch on the owner's dashboard. */
export interface DashboardBranch extends FleetCounts {
  branchCode: string
  branchName: string
}

/**
 * The month so far, from the first of the month up to and not including `to`.
 * `utilisationPercent` is null when there were no serviceable days.
 */
export interface MonthToDate {
  from: IsoDate
  to: IsoDate
  utilisationPercent: Percent | null
  grossContribution: Money
}

/**
 * `GET /api/admin/dashboard`. The business across all three branches today.
 * Reading it runs the lazy sweep first, so a lapsed hold or an overdue hire is
 * already counted where it now belongs.
 */
export interface AdminDashboard {
  date: IsoDate
  branches: DashboardBranch[]
  totals: FleetCounts
  monthToDate: MonthToDate
  openDamageReports: number
  customersOnHold: number
  failedNotifications: number
}
