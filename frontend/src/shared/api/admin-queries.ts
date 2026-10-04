/**
 * The owner's reads, as cached queries.
 *
 * Every key starts with the admin segment. The dashboard, the audit trail and
 * the notification log are never fresh, so a screen left open all day reads
 * them again whenever the window comes back into focus. The report is fresh for
 * a minute, because it covers a period and the server works it out over the
 * whole fleet. The catalogue, its categories and its models, is fresh for a
 * minute like the customer's catalogue. The asset register is never fresh,
 * because a unit moves at a counter while the owner reads it. Those rules live
 * in query-client.ts, and the key is all a query needs to get the right one.
 *
 * The CSV is not here. It is a file to save and not data to keep, so the
 * screen asks for it once for each press of the button.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { getAdminAsset, listAdminAssets } from './admin-assets'
import { getAdminModel, listAdminCategories, listAdminModels } from './admin-catalogue'
import { getAdminDashboard } from './admin-dashboard'
import { listAuditEvents, listNotifications } from './audit-log'
import type {
  AdminAssetDetail,
  AdminAssetQuery,
  AdminModel,
  AdminModelQuery,
  AuditEventQuery,
  EmailNotificationQuery,
  UtilisationReportQuery,
} from './contract'
import {
  ADMIN_ASSETS_SEGMENT,
  ADMIN_AUDIT_SEGMENT,
  ADMIN_CATALOGUE_SEGMENT,
  ADMIN_DASHBOARD_SEGMENT,
  ADMIN_KEY,
  ADMIN_NOTIFICATIONS_SEGMENT,
  ADMIN_REPORT_SEGMENT,
  ASSETS_KEY,
  CATALOGUE_KEY,
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

  /** Every category, switched on or not, each parent before its children. */
  categories: () =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_CATALOGUE_SEGMENT, 'categories'],
      queryFn: ({ signal }) => listAdminCategories(signal),
    }),

  /** One page of the product models, published or not. */
  models: (query: AdminModelQuery) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_CATALOGUE_SEGMENT, 'models', query],
      queryFn: ({ signal }) => listAdminModels(query, signal),
    }),

  /** One product model by its key. */
  model: (id: string) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_CATALOGUE_SEGMENT, 'model', id],
      queryFn: ({ signal }) => getAdminModel(id, signal),
    }),

  /** One page of the units of the fleet, retired or not, in tag order. */
  assets: (query: AdminAssetQuery) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_ASSETS_SEGMENT, 'page', query],
      queryFn: ({ signal }) => listAdminAssets(query, signal),
    }),

  /** One unit with its history, by its tag. */
  asset: (tag: string) =>
    queryOptions({
      queryKey: [ADMIN_KEY, ADMIN_ASSETS_SEGMENT, 'unit', tag],
      queryFn: ({ signal }) => getAdminAsset(tag, signal),
    }),
}

/**
 * Keep the unit a write answered with under its tag, so the screen shows the
 * unit as the server now has it at once, its moves and its history with it.
 */
export function rememberAdminAsset(client: QueryClient, unit: AdminAssetDetail): void {
  client.setQueryData(adminQueries.asset(unit.assetTag).queryKey, unit)
}

/**
 * Mark everything a write to the register changes as out of date. The pages
 * of the register, the owner's dashboard and report, which count units by
 * where they stand, the number of units each model holds in the catalogue,
 * the trail, which gained an event, and the counter's locator, which says
 * where each unit is.
 */
export function forgetTheRegister(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [ADMIN_KEY] })
  void client.invalidateQueries({ queryKey: [ASSETS_KEY] })
}

/**
 * Keep the model a write answered with under its key, so the form shows the
 * server's figures at once if it is opened again.
 */
export function rememberAdminModel(client: QueryClient, model: AdminModel): void {
  client.setQueryData(adminQueries.model(model.id).queryKey, model)
}

/**
 * Mark the catalogue as out of date after a write of the owner's. The owner's
 * lists are read again, and so is the catalogue customers browse, because a
 * new rate, a new name or a model shown or hidden reaches it at once. The
 * write added an event to the trail as well.
 */
export function forgetTheCatalogue(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [ADMIN_KEY, ADMIN_CATALOGUE_SEGMENT] })
  void client.invalidateQueries({ queryKey: [ADMIN_KEY, ADMIN_AUDIT_SEGMENT] })
  void client.invalidateQueries({ queryKey: [CATALOGUE_KEY] })
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
