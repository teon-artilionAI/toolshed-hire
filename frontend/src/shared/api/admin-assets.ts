/**
 * The owner's asset register. Every unit of the fleet, retired or not, its
 * paperwork, its history, and the moves through its lifecycle made by hand.
 *
 * Every route here is for an administrator, and the API refuses anyone else
 * with a 403. Each function makes one call and reads the body into its
 * contract type, checking every member, so a body that breaks the contract
 * fails here with the name of the field.
 *
 * Every rule about tags, money, meter readings and the lifecycle is the
 * server's. A refused field comes back as a 422 naming it, and a move the
 * unit may not make comes back as a 409 with the server's sentence. Nothing
 * here checks a figure or works one out, and nothing is ever deleted. A unit
 * leaves the fleet by being retired, and its row and history stay. Each write
 * is sent once for each press of a button and never repeated by the client,
 * because a request that timed out may still have reached the server.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  AdminAsset,
  AdminAssetDetail,
  AdminAssetPage,
  AdminAssetQuery,
  AssetChangesRequest,
  AssetHistoryEntry,
  AssetHistoryKind,
  AssetStatus,
  AssetTransitionRequest,
  NewAssetRequest,
} from './contract'
import { ASSET_STATUSES } from './locator'
import {
  readCount,
  readDate,
  readList,
  readMoney,
  readNullableCount,
  readNullableDate,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readText,
} from './read'
import { CONDITION_GRADES } from './rental-read'

const ASSETS_ENDPOINT = '/admin/assets'

/** How many units a page of the register holds. */
export const ASSET_PAGE_SIZE = 20

/** Where an entry of a unit's history can come from. */
export const HISTORY_KINDS: readonly AssetHistoryKind[] = ['ALLOCATION', 'RENTAL', 'DAMAGE_REPORT', 'AUDIT_EVENT']

/** A tag is user input by the time it reaches here, so it is always encoded. */
function unitPath(tag: string): string {
  return `${ASSETS_ENDPOINT}/${encodeURIComponent(tag)}`
}

/** One status of the list of moves a unit may make. */
function readMove(value: unknown, path: string): AssetStatus {
  const status = ASSET_STATUSES.find((known) => known === value)
  if (status === undefined) {
    throw malformedResponse(
      path,
      `Expected every member of allowedTransitions from ${path} to be one of ${ASSET_STATUSES.join(', ')}, got ${JSON.stringify(value)}.`,
    )
  }
  return status
}

/** The moment an entry of the history happened. The contract never sends it as null. */
function readMoment(record: Record<string, unknown>, path: string): string {
  const value = readNullableTimestamp(record, 'at', path)
  if (value === null) throw malformedResponse(path, `Expected field at from ${path} to be an instant, got null.`)
  return value
}

function readUnit(record: Record<string, unknown>, path: string): AdminAsset {
  return {
    id: readText(record, 'id', path),
    assetTag: readText(record, 'assetTag', path),
    modelId: readText(record, 'modelId', path),
    modelName: readText(record, 'modelName', path),
    modelSlug: readText(record, 'modelSlug', path),
    categoryName: readText(record, 'categoryName', path),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    serialNumber: readNullableText(record, 'serialNumber', path),
    status: readOneOf(record, 'status', path, ASSET_STATUSES),
    conditionGrade: readOneOf(record, 'conditionGrade', path, CONDITION_GRADES),
    acquiredOn: readDate(record, 'acquiredOn', path),
    acquisitionCost: readMoney(record, 'acquisitionCost', path),
    hourMeterReading: readNullableCount(record, 'hourMeterReading', path),
    notes: readNullableText(record, 'notes', path),
    retiredOn: readNullableDate(record, 'retiredOn', path),
    activeAllocationCount: readCount(record, 'activeAllocationCount', path),
    openDamageReports: readCount(record, 'openDamageReports', path),
    allowedTransitions: readList(record, 'allowedTransitions', path, readMove),
  }
}

function readAdminAsset(value: unknown, path: string): AdminAsset {
  return readUnit(readObject(value, path, 'a unit of the fleet'), path)
}

function readHistoryEntry(value: unknown, path: string): AssetHistoryEntry {
  const record = readObject(value, path, 'an entry of the history of a unit')
  return {
    at: readMoment(record, path),
    kind: readOneOf(record, 'kind', path, HISTORY_KINDS),
    summary: readText(record, 'summary', path),
    reference: readNullableText(record, 'reference', path),
  }
}

function readAdminAssetDetail(value: unknown, path: string): AdminAssetDetail {
  const record = readObject(value, path, 'a unit of the fleet with its history')
  return { ...readUnit(record, path), history: readList(record, 'history', path, readHistoryEntry) }
}

function readAssetPage(value: unknown, path: string): AdminAssetPage {
  const record = readObject(value, path, 'a page of the units of the fleet')
  return {
    items: readList(record, 'items', path, readAdminAsset),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/admin/assets. One page of the units that match, retired or not, in
 * tag order.
 *
 * @throws ApiError with status 422 naming a filter the server refused, and
 *   403 for anyone but an administrator.
 */
export function listAdminAssets(query: AdminAssetQuery, signal?: AbortSignal): Promise<AdminAssetPage> {
  return api.get(ASSETS_ENDPOINT, readAssetPage, { query, signal })
}

/**
 * GET /api/admin/assets/{tag}. One unit with its history, the newest first.
 *
 * @throws ApiError with status 404 when no unit carries the tag, and 403 for
 *   anyone but an administrator.
 */
export function getAdminAsset(tag: string, signal?: AbortSignal): Promise<AdminAssetDetail> {
  return api.get(unitPath(tag), readAdminAssetDetail, { signal })
}

/**
 * POST /api/admin/assets. Answers 201 with the new unit, at `INTAKE`, and its
 * history.
 *
 * @throws ApiError with status 422 naming the field the server refused, such
 *   as a tag another unit carries, and 403 for anyone but an administrator.
 */
export function registerAsset(body: NewAssetRequest): Promise<AdminAssetDetail> {
  return api.post(ASSETS_ENDPOINT, body, readAdminAssetDetail)
}

/**
 * PATCH /api/admin/assets/{tag}. Changes the fields sent and leaves the rest.
 *
 * @throws ApiError with status 422 naming the field the server refused, 404
 *   when no unit carries the tag, and 403 for anyone but an administrator.
 */
export function changeAsset(tag: string, changes: AssetChangesRequest): Promise<AdminAssetDetail> {
  return api.patch(unitPath(tag), changes, readAdminAssetDetail)
}

/**
 * POST /api/admin/assets/{tag}/transitions. Moves the unit to the status
 * named, and answers with the unit as it now stands and its history.
 *
 * @throws ApiError with status 409 when the unit may not make that move from
 *   where it stands or a booking still holds a unit being retired, 422 naming
 *   `to` or `reason`, 404 when no unit carries the tag, and 403 for anyone but
 *   an administrator.
 */
export function moveAsset(tag: string, move: AssetTransitionRequest): Promise<AdminAssetDetail> {
  return api.post(`${unitPath(tag)}/transitions`, move, readAdminAssetDetail)
}
