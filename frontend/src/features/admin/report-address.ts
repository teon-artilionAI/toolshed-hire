/**
 * What the SC-22 report shows, read from the address and written back to it.
 *
 * The period, the grouping, the branch and category filters and the page all
 * live in the address, so a reload or a shared link shows the same figures.
 * The names are the ones the API takes, so the address reads like the query.
 *
 * The period defaults to the last full calendar month, from its first day up
 * to and not including the first day of this month, at the branches. That is
 * the question the owner asks most, "how did last month go". A period in the
 * address that is not two days on the calendar falls back to that default as
 * a whole, so half of one period is never mixed with half of another. Whether
 * the period is long enough, short enough or the right way round is the
 * server's to say, and it says so with a 422 that the screen puts under the
 * field. The browser holds no copy of that rule.
 */

import type { IsoDate, ReportGrouping, UtilisationCsvQuery, UtilisationReportQuery } from '../../shared/api/contract'
import { REPORT_GROUPINGS } from '../../shared/api/reporting'

/** The names the report keeps in the address. */
export const REPORT_PARAMETER = {
  from: 'from',
  to: 'to',
  groupBy: 'groupBy',
  branchCode: 'branchCode',
  categorySlug: 'categorySlug',
  page: 'page',
} as const

/** The values the server can refuse that have a control on the screen, by the
 *  names it gives them. A message about any other is listed apart. */
export const REPORT_FIELDS: readonly string[] = [
  REPORT_PARAMETER.from,
  REPORT_PARAMETER.to,
  REPORT_PARAMETER.groupBy,
  REPORT_PARAMETER.branchCode,
  REPORT_PARAMETER.categorySlug,
]

/** Pages are counted from one. */
export const FIRST_PAGE = 1

/** How many rows a page of the report holds. The chart draws the same rows,
 *  so a page has to stay short enough to read as one chart. */
export const REPORT_PAGE_SIZE = 20

/** A model is the level the owner asks about first, "which tools earn their keep". */
export const DEFAULT_GROUPING: ReportGrouping = 'model'

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/
const ISO_DATE_LENGTH = 10
const MONTHS_IN_YEAR = 12
const JANUARY = 1
const YEAR_DIGITS = 4
const MONTH_DIGITS = 2

/** What the report shows. A filter that is null is not applied. */
export interface ReportFilters {
  from: IsoDate
  to: IsoDate
  groupBy: ReportGrouping
  branchCode: string | null
  categorySlug: string | null
  page: number
}

/** Whether a value is a day on the calendar written `YYYY-MM-DD`. */
function isCalendarDate(value: string | null): value is IsoDate {
  if (value === null || !DATE_SHAPE.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  // A day such as 31 September parses as 1 October, so it is read back and
  // compared, and only a day that comes back as written is a day.
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, ISO_DATE_LENGTH) === value
}

function pad(value: number, digits: number): string {
  return String(value).padStart(digits, '0')
}

/**
 * The last full calendar month before the month a day falls in.
 *
 * @param today A day as `YYYY-MM-DD`, today at the branches.
 * @returns Its first day and the first day of the month after it, so the
 *   period is `[from, to)` the way the API counts it.
 */
export function lastFullMonth(today: IsoDate): { from: IsoDate; to: IsoDate } {
  const [year, month] = today.split('-').map(Number)
  const previousYear = month === JANUARY ? year - 1 : year
  const previousMonth = month === JANUARY ? MONTHS_IN_YEAR : month - 1
  return {
    from: `${pad(previousYear, YEAR_DIGITS)}-${pad(previousMonth, MONTH_DIGITS)}-01`,
    to: `${pad(year, YEAR_DIGITS)}-${pad(month, MONTH_DIGITS)}-01`,
  }
}

function readGrouping(value: string | null): ReportGrouping | null {
  return REPORT_GROUPINGS.find((grouping) => grouping === value) ?? null
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

function readFilter(value: string | null): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

/**
 * Read what the report shows from the address.
 *
 * @param today Today at the branches, for the default period.
 */
export function readReportFilters(params: URLSearchParams, today: IsoDate): ReportFilters {
  const from = params.get(REPORT_PARAMETER.from)
  const to = params.get(REPORT_PARAMETER.to)
  const period = isCalendarDate(from) && isCalendarDate(to) ? { from, to } : lastFullMonth(today)
  return {
    ...period,
    groupBy: readGrouping(params.get(REPORT_PARAMETER.groupBy)) ?? DEFAULT_GROUPING,
    branchCode: readFilter(params.get(REPORT_PARAMETER.branchCode)),
    categorySlug: readFilter(params.get(REPORT_PARAMETER.categorySlug)),
    page: readPage(params.get(REPORT_PARAMETER.page)),
  }
}

/**
 * Write what the report shows as an address. The period and the grouping are
 * always written, so the address names the figures whatever day it is opened.
 * A filter that is not applied and the first page are left out.
 */
export function writeReportFilters(filters: ReportFilters): URLSearchParams {
  const written = new URLSearchParams()
  written.set(REPORT_PARAMETER.from, filters.from)
  written.set(REPORT_PARAMETER.to, filters.to)
  written.set(REPORT_PARAMETER.groupBy, filters.groupBy)
  if (filters.branchCode !== null) written.set(REPORT_PARAMETER.branchCode, filters.branchCode)
  if (filters.categorySlug !== null) written.set(REPORT_PARAMETER.categorySlug, filters.categorySlug)
  if (filters.page > FIRST_PAGE) written.set(REPORT_PARAMETER.page, String(filters.page))
  return written
}

/** Whether the address already says exactly what the report shows. When it
 *  does not, the screen writes it out, so a link copied from it is complete. */
export function addressSays(params: URLSearchParams, filters: ReportFilters): boolean {
  return params.toString() === writeReportFilters(filters).toString()
}

/** The query for one page of the report. */
export function reportQueryFor(filters: ReportFilters): UtilisationReportQuery {
  return { ...csvQueryFor(filters), page: filters.page, pageSize: REPORT_PAGE_SIZE }
}

/** The query for the CSV, which holds every row and has no page. */
export function csvQueryFor(filters: ReportFilters): UtilisationCsvQuery {
  return {
    from: filters.from,
    to: filters.to,
    groupBy: filters.groupBy,
    branchCode: filters.branchCode ?? undefined,
    categorySlug: filters.categorySlug ?? undefined,
  }
}
