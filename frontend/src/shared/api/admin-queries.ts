/**
 * The owner's reads, as cached queries.
 *
 * Every key starts with the admin segment. The dashboard, the audit trail and
 * the notification log are never fresh, so a screen left open all day reads
 * them again whenever the window comes back into focus. The report is fresh for
 * a minute, because it covers a period and the server works it out over the
 * whole fleet. Those rules live in query-client.ts, and the key is all a query
 * needs to get the right one.
 *
 * The CSV is not here. It is a file to save and not data to keep, so the
 * screen asks for it once for each press of the button.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { getAdminDashboard } from './admin-dashboard'
import { listAuditEvents, listNotifications } from './audit-log'
import type { AuditEventQuery, EmailNotificationQuery, UtilisationReportQuery } from './contract'
import {
  ADMIN_AUDIT_SEGMENT,
  ADMIN_DASHBOARD_SEGMENT,
  ADMIN_KEY,
  ADMIN_NOTIFICATIONS_SEGMENT,
  ADMIN_REPORT_SEGMENT,
} from './query-client'
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

  /** One page of the audit trail, newest first. */
  auditEvents: (query: AuditEventQuery) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_AUDIT_SEGMENT, query],
      queryFn: ({ signal }) => listAuditEvents(query, signal),
    }),

  /** One page of the notification log, newest first. */
  notifications: (query: EmailNotificationQuery) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_NOTIFICATIONS_SEGMENT, query],
      queryFn: ({ signal }) => listNotifications(query, signal),
    }),
}

/**
 * Mark everything the owner reads as out of date after a write of the owner's.
 * A correction or a release changes the figures on the dashboard and in the
 * report, and adds an event to the trail, so each is asked for again the next
 * time a screen shows it.
 */
export function forgetOwnerFigures(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [ADMIN_KEY] })
}

/**
 * Mark the notification log as out of date after a re-send. The new email is
 * on the first page of the log, newest first, and only the server knows which
 * page every other one now falls on. The trail gained an event as well.
 */
export function forgetTheLog(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [ADMIN_KEY, ADMIN_NOTIFICATIONS_SEGMENT] })
  void client.invalidateQueries({ queryKey: [ADMIN_KEY, ADMIN_AUDIT_SEGMENT] })
  void client.invalidateQueries({ queryKey: [ADMIN_KEY, ADMIN_DASHBOARD_SEGMENT] })
}
