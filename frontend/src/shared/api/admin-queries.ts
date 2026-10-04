/**
 * The owner's reads, as cached queries.
 *
 * Both keys start with the admin segment. The dashboard is never fresh, so a
 * screen left open all day reads it again whenever the window comes back into
 * focus. The report is fresh for a minute, because it covers a period and the
 * server works it out over the whole fleet. Those rules live in
 * query-client.ts, and the key is all a query needs to get the right one.
 *
 * The CSV is not here. It is a file to save and not data to keep, so the
 * screen asks for it once for each press of the button.
 */

import { queryOptions } from '@tanstack/react-query'
import { getAdminDashboard } from './admin-dashboard'
import type { UtilisationReportQuery } from './contract'
import { ADMIN_DASHBOARD_SEGMENT, ADMIN_KEY, ADMIN_REPORT_SEGMENT } from './query-client'
import { getUtilisationReport } from './reporting'

export const adminQueries = {
  /** The business across all three branches today. */
  dashboard: () =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_DASHBOARD_SEGMENT],
      queryFn: ({ signal }) => getAdminDashboard(signal),
    }),

  /** One page of the utilisation and gross contribution report. */
  report: (query: UtilisationReportQuery) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_REPORT_SEGMENT, query],
      queryFn: ({ signal }) => getUtilisationReport(query, signal),
    }),
}
