/**
 * The utilisation and gross contribution report, for the owner.
 *
 * Two routes. One reads a page of rows with the totals over every row, and the
 * other sends every row as a CSV file. Each function makes one call. The read
 * checks every member of the body, so a body that breaks the contract fails
 * here with the name of the field. The CSV goes through the same client, with
 * the same token and the same renewal, and comes back as the bytes and the
 * name the server gave the file.
 *
 * Every figure is the server's. Nothing here or above it adds anything up, and
 * the rows stay in the order the server sent them, highest gross contribution
 * first.
 */

import { api } from './client'
import type { ApiFile } from './client'
import type {
  AssetStatus,
  ReportDefinitions,
  ReportFigures,
  ReportGrouping,
  ReportRow,
  UtilisationCsvQuery,
  UtilisationReport,
  UtilisationReportQuery,
} from './contract'
import { ASSET_STATUSES } from './locator'
import {
  readCount,
  readDate,
  readList,
  readNullablePercent,
  readObject,
  readOneOf,
  readSignedMoney,
  readText,
} from './read'

const REPORT_ENDPOINT = '/admin/reports/utilisation'
const CSV_ENDPOINT = '/admin/reports/utilisation.csv'

/** What the CSV route sends, and the problem document it sends instead when it refuses. */
const CSV_ACCEPT = 'text/csv, application/problem+json'

/** The levels the report can be grouped at, in the order the screen offers them. */
export const REPORT_GROUPINGS: readonly ReportGrouping[] = ['asset', 'model', 'category', 'branch']

function readDefinitions(value: unknown, path: string): ReportDefinitions {
  const record = readObject(value, path, 'the definitions of the report')
  return {
    utilisation: readText(record, 'utilisation', path),
    grossContribution: readText(record, 'grossContribution', path),
  }
}

/**
 * Every amount is read as money that may run below zero. Gross contribution
 * does whenever repairs cost more than a unit brought in. The others are sums
 * of charges, and a reversal of a charge is a charge with a minus sign, so a
 * period can in principle net below zero too. The screen writes the sign as
 * it came, and one such cell is no reason to refuse the whole report.
 */
function readFigures(record: Record<string, unknown>, path: string): ReportFigures {
  return {
    assetCount: readCount(record, 'assetCount', path),
    daysOnHire: readCount(record, 'daysOnHire', path),
    serviceableDays: readCount(record, 'serviceableDays', path),
    utilisationPercent: readNullablePercent(record, 'utilisationPercent', path),
    hireRevenueExVat: readSignedMoney(record, 'hireRevenueExVat', path),
    lateFeesExVat: readSignedMoney(record, 'lateFeesExVat', path),
    damageRecoveryExVat: readSignedMoney(record, 'damageRecoveryExVat', path),
    repairCosts: readSignedMoney(record, 'repairCosts', path),
    grossContribution: readSignedMoney(record, 'grossContribution', path),
  }
}

/**
 * A member that names where a row sits, which does not apply at every
 * grouping. The contract writes it as null where it does not apply, and I also
 * take it being left out as null, because a row for a model has no tag either
 * way and nothing on the screen reads the difference.
 */
function readPlace(record: Record<string, unknown>, key: string, path: string): string | null {
  return record[key] === undefined || record[key] === null ? null : readText(record, key, path)
}

function readStatus(record: Record<string, unknown>, path: string): AssetStatus | null {
  return record.status === undefined || record.status === null
    ? null
    : readOneOf(record, 'status', path, ASSET_STATUSES)
}

function readRow(value: unknown, path: string): ReportRow {
  const record = readObject(value, path, 'a row of the report')
  return {
    key: readText(record, 'key', path),
    label: readText(record, 'label', path),
    branchCode: readPlace(record, 'branchCode', path),
    categoryName: readPlace(record, 'categoryName', path),
    modelName: readPlace(record, 'modelName', path),
    assetTag: readPlace(record, 'assetTag', path),
    status: readStatus(record, path),
    ...readFigures(record, path),
  }
}

function readReport(value: unknown, path: string): UtilisationReport {
  const record = readObject(value, path, 'a utilisation and gross contribution report')
  return {
    from: readDate(record, 'from', path),
    to: readDate(record, 'to', path),
    groupBy: readOneOf(record, 'groupBy', path, REPORT_GROUPINGS),
    definitions: readDefinitions(record.definitions, path),
    totals: readFigures(readObject(record.totals, path, 'the totals of the report'), path),
    items: readList(record, 'items', path, readRow),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/admin/reports/utilisation. One page of rows and the totals.
 *
 * @throws ApiError with status 422 naming the field when the period, the
 *   grouping or a filter is refused, and 403 for anyone but an administrator.
 */
export function getUtilisationReport(query: UtilisationReportQuery, signal?: AbortSignal): Promise<UtilisationReport> {
  return api.get(REPORT_ENDPOINT, readReport, { query, signal })
}

/**
 * GET /api/admin/reports/utilisation.csv. Every row of the report as a file,
 * with the name the server gave it.
 *
 * @throws ApiError as the report does, and of kind `malformed` when the answer
 *   does not name its file.
 */
export function downloadUtilisationCsv(query: UtilisationCsvQuery): Promise<ApiFile> {
  return api.getFile(CSV_ENDPOINT, CSV_ACCEPT, { query })
}
