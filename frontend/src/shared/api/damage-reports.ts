/**
 * The damage report routes. Filing a report, listing and reading the reports
 * of a unit, and the owner's two moves, sending a report for repair and
 * resolving it.
 *
 * Filing is for staff at the branch that holds the unit, and the two moves are
 * for an administrator. Each write answers with the report as the server now
 * has it. Filing also quarantines the unit, raises the recovery charge on the
 * hire and settles its deposit when nothing else is waiting, all in the same
 * transaction, so a screen reads the hire again afterwards rather than working
 * any of that out.
 *
 * A write is sent once for each press of a button. The client never repeats a
 * POST by itself, because a request that timed out may still have reached the
 * server and raised the charge.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  DamageReport,
  DamageReportListQuery,
  DamageReportPage,
  DamageSeverity,
  DamageStatus,
  FileDamageReportRequest,
  IsoTimestamp,
  ResolveDamageReportRequest,
} from './contract'
import {
  readCount,
  readFlag,
  readList,
  readMoney,
  readNullableMoney,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readText,
} from './read'

const DAMAGE_REPORTS_ENDPOINT = '/damage-reports'

/** Every severity a report can have, least bad first. */
export const DAMAGE_SEVERITIES: readonly DamageSeverity[] = ['MINOR', 'MAJOR', 'WRITE_OFF']

/** Every status a report can be in, in the order a report moves through them. */
export const DAMAGE_STATUSES: readonly DamageStatus[] = ['OPEN', 'UNDER_REPAIR', 'RESOLVED', 'WRITTEN_OFF']

/** The statuses of a report that is still being dealt with. */
export const OPEN_DAMAGE_STATUSES: readonly DamageStatus[] = ['OPEN', 'UNDER_REPAIR']

/** The page size the list of a unit's reports asks for. The API's own default. */
export const DAMAGE_REPORT_PAGE_SIZE = 20

/** An instant the contract never sends as null. */
function readTimestamp(record: Record<string, unknown>, key: string, path: string): IsoTimestamp {
  const value = readNullableTimestamp(record, key, path)
  if (value === null) {
    throw malformedResponse(path, `Expected field ${key} from ${path} to be an instant, got null.`)
  }
  return value
}

/** Read one report, checking every member the contract names. */
export function readDamageReport(value: unknown, path: string): DamageReport {
  const record = readObject(value, path, 'a damage report')
  return {
    id: readText(record, 'id', path),
    reference: readText(record, 'reference', path),
    assetTag: readText(record, 'assetTag', path),
    modelName: readText(record, 'modelName', path),
    branchCode: readText(record, 'branchCode', path),
    rentalId: readNullableText(record, 'rentalId', path),
    rentalReference: readNullableText(record, 'rentalReference', path),
    rentalItemId: readNullableText(record, 'rentalItemId', path),
    severity: readOneOf(record, 'severity', path, DAMAGE_SEVERITIES),
    status: readOneOf(record, 'status', path, DAMAGE_STATUSES),
    description: readText(record, 'description', path),
    repairEstimate: readMoney(record, 'repairEstimate', path),
    actualRepairCost: readNullableMoney(record, 'actualRepairCost', path),
    chargeableToCustomer: readFlag(record, 'chargeableToCustomer', path),
    recoveryCharged: readNullableMoney(record, 'recoveryCharged', path),
    replacementValue: readMoney(record, 'replacementValue', path),
    reportedAt: readTimestamp(record, 'reportedAt', path),
    reportedByName: readText(record, 'reportedByName', path),
    resolvedAt: readNullableTimestamp(record, 'resolvedAt', path),
    resolutionNotes: readNullableText(record, 'resolutionNotes', path),
  }
}

function readDamageReportPage(value: unknown, path: string): DamageReportPage {
  const record = readObject(value, path, 'a page of damage reports')
  return {
    items: readList(record, 'items', path, readDamageReport),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/** A key or a reference is user input by the time it reaches here, so it is
 *  always encoded. */
function reportEndpoint(idOrReference: string): string {
  return `${DAMAGE_REPORTS_ENDPOINT}/${encodeURIComponent(idOrReference)}`
}

/**
 * GET /api/damage-reports. The reports that match, newest first.
 *
 * @throws ApiError with status 403 for a customer.
 */
export function listDamageReports(query: DamageReportListQuery, signal?: AbortSignal): Promise<DamageReportPage> {
  return api.get(DAMAGE_REPORTS_ENDPOINT, readDamageReportPage, { query, signal })
}

/**
 * POST /api/damage-reports. Files a report and quarantines the unit.
 *
 * @throws ApiError with status 422 for a refused value, among them a missing
 *   decision on charging and an amount above the replacement value, 403 at
 *   another branch, and 409 when the unit cannot take a report now.
 */
export function fileDamageReport(body: FileDamageReportRequest): Promise<DamageReport> {
  return api.post(DAMAGE_REPORTS_ENDPOINT, body, readDamageReport)
}

/**
 * POST /api/damage-reports/{id}/repair. No body. Moves an open report, and
 * the unit with it, to the workshop.
 *
 * @throws ApiError with status 409 when the report is not open, and 403 for
 *   anyone but an administrator.
 */
export function sendForRepair(idOrReference: string): Promise<DamageReport> {
  return api.post(`${reportEndpoint(idOrReference)}/repair`, undefined, readDamageReport)
}

/**
 * POST /api/damage-reports/{id}/resolution. Closes a report as repaired or
 * written off.
 *
 * @throws ApiError with status 422 for a repaired report with no cost, 409 for
 *   a report already closed or a write off while the unit is set aside for a
 *   booking, and 403 for anyone but an administrator.
 */
export function resolveDamageReport(idOrReference: string, body: ResolveDamageReportRequest): Promise<DamageReport> {
  return api.post(`${reportEndpoint(idOrReference)}/resolution`, body, readDamageReport)
}
