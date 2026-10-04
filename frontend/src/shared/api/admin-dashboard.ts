/**
 * The owner's dashboard. The business across all three branches today.
 *
 * One read. The server runs its lazy sweep before it answers, so a hold that
 * has lapsed or a hire that has gone overdue is already counted where it now
 * belongs. The function makes one call and reads the body into its contract
 * type, checking every member, so a body that breaks the contract fails here
 * with the name of the field.
 *
 * Every count, the month's utilisation and its gross contribution are the
 * server's. Nothing here or above it adds anything up, and the totals are the
 * server's totals and not a sum of the branches.
 */

import { api } from './client'
import type { AdminDashboard, DashboardBranch, FleetCounts, MonthToDate } from './contract'
import { readCount, readDate, readList, readNullablePercent, readObject, readSignedMoney, readText } from './read'

const DASHBOARD_ENDPOINT = '/admin/dashboard'

function readCounts(record: Record<string, unknown>, path: string): FleetCounts {
  return {
    collectionsDue: readCount(record, 'collectionsDue', path),
    returnsDue: readCount(record, 'returnsDue', path),
    overdue: readCount(record, 'overdue', path),
    onHire: readCount(record, 'onHire', path),
    quarantined: readCount(record, 'quarantined', path),
    underRepair: readCount(record, 'underRepair', path),
    available: readCount(record, 'available', path),
  }
}

function readBranch(value: unknown, path: string): DashboardBranch {
  const record = readObject(value, path, 'a branch on the dashboard')
  return {
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    ...readCounts(record, path),
  }
}

function readMonthToDate(value: unknown, path: string): MonthToDate {
  const record = readObject(value, path, 'the month so far')
  return {
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    utilisationPercent: readNullablePercent(record, 'utilisationPercent', path),
    grossContribution: readSignedMoney(record, 'grossContribution', path),
  }
}

function readDashboard(value: unknown, path: string): AdminDashboard {
  const record = readObject(value, path, "the owner's dashboard")
  return {
    date: readDate(record, 'date', path),
    branches: readList(record, 'branches', path, readBranch),
    totals: readCounts(readObject(record.totals, path, 'the totals of the dashboard'), path),
    monthToDate: readMonthToDate(record.monthToDate, path),
    openDamageReports: readCount(record, 'openDamageReports', path),
    customersOnHold: readCount(record, 'customersOnHold', path),
    failedNotifications: readCount(record, 'failedNotifications', path),
  }
}

/**
 * GET /api/admin/dashboard.
 *
 * @throws ApiError with status 403 for anyone but an administrator.
 */
export function getAdminDashboard(signal?: AbortSignal): Promise<AdminDashboard> {
  return api.get(DASHBOARD_ENDPOINT, readDashboard, { signal })
}
