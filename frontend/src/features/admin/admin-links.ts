/**
 * Where the owner's screens send a person, written in one place.
 *
 * The dashboard links each figure to the screen the owner would open next,
 * with the filters that show what the figure counts.
 */

import type { IsoDate, ReportGrouping } from '../../shared/api/contract'
import { writeNotificationFilters } from './audit-address'
import { FIRST_PAGE, writeReportFilters } from './report-address'
import { holdsHref } from './users-address'

/** SC-22, the utilisation and gross contribution report. */
export const REPORT_PATH = '/admin/reports'

/** SC-21, the asset register, where each unit's open damage reports are
 *  listed with a link to the damage screen that resolves them. */
export const ASSET_REGISTER_PATH = '/admin/assets'

/** SC-23, the staff accounts and the customer holds. */
export const USERS_PATH = '/admin/users'

/** SC-23 on the customer holds, showing the customers who are on hold, which
 *  are the ones the owner can release. */
export const CUSTOMER_HOLDS_HREF = holdsHref(USERS_PATH, 'ON_HOLD')

/** SC-24, where the audit trail and the notification log are. */
export const AUDIT_LOG_PATH = '/admin/audit'

/** SC-24 on the notification log, showing only the emails that failed, which
 *  are the ones the owner can send again. */
export const FAILED_NOTIFICATIONS_HREF = `${AUDIT_LOG_PATH}?${writeNotificationFilters({
  status: 'FAILED',
  page: FIRST_PAGE,
}).toString()}`

/**
 * SC-22 for one period at one grouping, with no filter, from the first page.
 *
 * @param period The period as the API counts it, `[from, to)`.
 */
export function reportHref(period: { from: IsoDate; to: IsoDate }, groupBy: ReportGrouping): string {
  const query = writeReportFilters({ ...period, groupBy, branchCode: null, categorySlug: null, page: FIRST_PAGE })
  return `${REPORT_PATH}?${query.toString()}`
}
