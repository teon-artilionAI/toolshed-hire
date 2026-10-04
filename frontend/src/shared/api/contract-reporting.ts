/**
 * The reporting wire types. The utilisation and gross contribution report, its
 * CSV, and the owner's dashboard.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoDate, JsonOf, Money, Paths, QueryOf, Refine, Schemas } from './contract-kit'

/**
 * A percentage as the API writes it, a string with two decimals such as
 * "15.78". The generated type is a plain `string`. I keep the name so a rate
 * reads as a rate, and it stays a string all the way to the screen, like money.
 */
export type Percent = string

/** The levels the report can be grouped at. `asset` is one row per unit. */
export type ReportGrouping = Schemas['GroupBy']

/**
 * The query `GET /api/admin/reports/utilisation` accepts.
 *
 * `from` and `to` are required, and `to` is not counted, so the period is
 * `[from, to)`. The server refuses a `to` that is not after `from` and a period
 * longer than 366 days, with a 422 naming `to`. The two filters are optional,
 * and a category takes in the categories directly under it. `pageSize` is 1 to
 * 100. The generated type lets the grouping, the page and its size be left
 * out, and the screens always send all three, so here each is required.
 */
export type UtilisationReportQuery = Refine<
  QueryOf<Paths['/api/admin/reports/utilisation']['get']>,
  { from: IsoDate; to: IsoDate; groupBy: ReportGrouping; page: number; pageSize: number }
>

/**
 * The query of the CSV route. The same as the report's, with every row and no
 * page. The screens always send the grouping, so here it is required.
 */
export type UtilisationCsvQuery = Refine<
  QueryOf<Paths['/api/admin/reports/utilisation.csv']['get']>,
  { from: IsoDate; to: IsoDate; groupBy: ReportGrouping }
>

/** The two definitions, in the server's own words. A screen shows them in full. */
export type ReportDefinitions = Schemas['ReportDefinitionsResponse']

/**
 * The amounts and the rate of a set of figures, under the names that say
 * what each one is. The generated type calls every one of them a `string`.
 */
interface NamedFigures {
  utilisationPercent: Percent | null
  hireRevenueExVat: Money
  lateFeesExVat: Money
  damageRecoveryExVat: Money
  repairCosts: Money
  grossContribution: Money
}

/**
 * The figures of the whole report.
 *
 * `utilisationPercent` is null when there were no serviceable days. Gross
 * contribution is the revenue less the repair costs, so it can run below
 * zero, and it is never profit. The other amounts are sums of charges and are
 * read as able to run below zero as well. Every figure is the server's, and
 * the browser adds none of them up.
 */
export type ReportFigures = Refine<Schemas['ReportFiguresResponse'], NamedFigures>

/**
 * One row of the report, with the same figures as the totals.
 *
 * `key` and `label` say what the row is at its grouping. The other members
 * name where it sits, and the server always sends each of them, null where it
 * does not apply. `assetTag` and `status` are set on a row for a unit.
 * `branchCode` is set on a row for a unit or a branch, `categoryName` on a row
 * for a unit, a model or a category, and `modelName` on a row for a unit or a
 * model.
 */
export type ReportRow = Refine<Schemas['ReportLineResponse'], NamedFigures>

/**
 * `GET /api/admin/reports/utilisation`. One page of rows, highest gross
 * contribution first, with the totals over every row and not only the page.
 * The server runs the lazy sweep before it works the figures out.
 */
export type UtilisationReport = Refine<
  JsonOf<Paths['/api/admin/reports/utilisation']['get']>,
  { from: IsoDate; to: IsoDate; totals: ReportFigures; items: ReportRow[] }
>

/** What is due and where the fleet stands, at one branch or across all of them, today. */
export type FleetCounts = Schemas['BranchCountsResponse']

/** One branch on the owner's dashboard. */
export type DashboardBranch = Schemas['BranchPositionResponse']

/**
 * The month so far, from the first of the month up to and not including `to`,
 * which is tomorrow. `utilisationPercent` is null when there were no
 * serviceable days.
 */
export type MonthToDate = Refine<
  Schemas['MonthToDateResponse'],
  { from: IsoDate; to: IsoDate; utilisationPercent: Percent | null; grossContribution: Money }
>

/**
 * `GET /api/admin/dashboard`. The business across all three branches today.
 * Reading it runs the lazy sweep first, so a lapsed hold or an overdue hire is
 * already counted where it now belongs.
 */
export type AdminDashboard = Refine<
  JsonOf<Paths['/api/admin/dashboard']['get']>,
  { date: IsoDate; branches: DashboardBranch[]; totals: FleetCounts; monthToDate: MonthToDate }
>
