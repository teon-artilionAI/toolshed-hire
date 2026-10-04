/**
 * Where the owner's screens send a person, written in one place.
 *
 * The dashboard links each figure to the screen the owner would open next.
 * Some of those screens still show sample data until a later change connects
 * them, and the shell says so above them, so a link to one is still the right
 * way to go.
 */

import type { IsoDate, ReportGrouping } from '../../shared/api/contract'
import { FIRST_PAGE, writeReportFilters } from './report-address'

/** SC-22, the utilisation and gross contribution report. */
export const REPORT_PATH = '/admin/reports'

/** SC-21, the asset register, where a unit with a damage report is dealt with. */
export const ASSET_REGISTER_PATH = '/admin/assets'

/** SC-23, where the customer holds are lifted. */
export const CUSTOMER_HOLDS_PATH = '/admin/users'

/** SC-24, where the notification log is. */
export const NOTIFICATION_LOG_PATH = '/admin/audit'

/**
 * SC-22 for one period at one grouping, with no filter, from the first page.
 *
 * @param period The period as the API counts it, `[from, to)`.
 */
export function reportHref(period: { from: IsoDate; to: IsoDate }, groupBy: ReportGrouping): string {
  const query = writeReportFilters({ ...period, groupBy, branchCode: null, categorySlug: null, page: FIRST_PAGE })
  return `${REPORT_PATH}?${query.toString()}`
}
