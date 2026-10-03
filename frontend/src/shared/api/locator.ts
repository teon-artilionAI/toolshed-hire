/**
 * The asset locator route, for staff at any branch.
 *
 * One read. It finds the units whose tag or model name matches what was typed,
 * at every branch, and says where each one is and what state it is in. It
 * changes nothing. The function makes one call and reads the body into its
 * contract type, checking every member.
 */

import { api } from './client'
import type { AssetStatus, LocatedUnit, LocatorPage, LocatorQuery } from './contract'
import {
  readCount,
  readList,
  readNullableDate,
  readNullableText,
  readObject,
  readOneOf,
  readText,
} from './read'
import { CONDITION_GRADES } from './rental-read'

const LOCATOR_ENDPOINT = '/assets/locator'

/** The shortest search the API accepts. */
export const MIN_LOCATOR_SEARCH_LENGTH = 2

/** The longest search the API accepts. */
export const MAX_LOCATOR_SEARCH_LENGTH = 80

/** Every state a unit can be in, in the order a unit usually moves through them. */
const ASSET_STATUSES: readonly AssetStatus[] = [
  'INTAKE',
  'AVAILABLE',
  'ON_HIRE',
  'QUARANTINED',
  'UNDER_REPAIR',
  'LOST',
  'RETIRED',
]

function readLocatedUnit(value: unknown, path: string): LocatedUnit {
  const record = readObject(value, path, 'a unit the locator found')
  return {
    assetTag: readText(record, 'assetTag', path),
    modelName: readText(record, 'modelName', path),
    modelSlug: readText(record, 'modelSlug', path),
    categoryName: readText(record, 'categoryName', path),
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    status: readOneOf(record, 'status', path, ASSET_STATUSES),
    conditionGrade: readOneOf(record, 'conditionGrade', path, CONDITION_GRADES),
    dueBackOn: readNullableDate(record, 'dueBackOn', path),
    rentalReference: readNullableText(record, 'rentalReference', path),
  }
}

function readLocatorPage(value: unknown, path: string): LocatorPage {
  const record = readObject(value, path, 'a page of located units')
  return {
    items: readList(record, 'items', path, readLocatedUnit),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

/**
 * GET /api/assets/locator. The units that match, at every branch.
 *
 * @throws ApiError with status 422 when the search is shorter than two
 *   characters or longer than eighty, and 403 for a customer. The screen never
 *   sends fewer than `MIN_LOCATOR_SEARCH_LENGTH`.
 */
export function locateUnits(query: LocatorQuery, signal?: AbortSignal): Promise<LocatorPage> {
  return api.get(LOCATOR_ENDPOINT, readLocatorPage, { query, signal })
}
