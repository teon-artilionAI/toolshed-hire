/**
 * What SC-21 shows, read from the address and written back to it.
 *
 * The search, the branch, the status, the model and the page live in the
 * address under the names the API takes, so a reload or a shared link shows
 * the same units. The unit open beside the list is there too, as `asset`,
 * which holds its tag, and the registration form is open while `add` says
 * `unit`. Opening one closes the other, so the address only ever names what is
 * on the screen.
 *
 * A filter the address names is passed to the server as it stands, apart from
 * a status the register does not have and a page that is not a whole number
 * from one, which are left out. Whether a filter makes sense is the server's
 * to say, with a 422 that the screen puts under the control.
 */

import { ASSET_PAGE_SIZE } from '../../shared/api/admin-assets'
import type { AdminAssetQuery, AssetStatus } from '../../shared/api/contract'
import { ASSET_STATUSES } from '../../shared/api/locator'
import { ASSET_REGISTER_PATH } from './admin-links'
import { FIRST_PAGE } from './report-address'

/** The names the register keeps in the address. */
export const ASSET_PARAMETER = {
  q: 'q',
  branchCode: 'branchCode',
  status: 'status',
  modelId: 'modelId',
  page: 'page',
  asset: 'asset',
  add: 'add',
} as const

/** The filters that have a control on the screen, by the names the server
 *  gives them. A refusal of any other is listed apart. */
export const ASSET_FILTER_FIELDS: readonly string[] = [
  ASSET_PARAMETER.q,
  ASSET_PARAMETER.branchCode,
  ASSET_PARAMETER.status,
  ASSET_PARAMETER.modelId,
]

/** The value of `add` while a unit is being registered. */
export const ADDING_A_UNIT = 'unit'

/** What the register shows, and what is open beside it. A filter that is
 *  null is not applied. */
export interface AssetFilters {
  q: string | null
  branchCode: string | null
  status: AssetStatus | null
  modelId: string | null
  page: number
  /** The tag of the unit open beside the list, or null. */
  asset: string | null
  /** Whether the registration form is open. */
  adding: boolean
}

/** The whole register from its first page, with nothing open. */
export const NO_ASSET_FILTERS: AssetFilters = {
  q: null,
  branchCode: null,
  status: null,
  modelId: null,
  page: FIRST_PAGE,
  asset: null,
  adding: false,
}

function readFilter(value: string | null): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

function readStatus(value: string | null): AssetStatus | null {
  return ASSET_STATUSES.find((status) => status === value) ?? null
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

/** Read what the register shows from the address. */
export function readAssetFilters(params: URLSearchParams): AssetFilters {
  const asset = readFilter(params.get(ASSET_PARAMETER.asset))
  return {
    q: readFilter(params.get(ASSET_PARAMETER.q)),
    branchCode: readFilter(params.get(ASSET_PARAMETER.branchCode)),
    status: readStatus(params.get(ASSET_PARAMETER.status)),
    modelId: readFilter(params.get(ASSET_PARAMETER.modelId)),
    page: readPage(params.get(ASSET_PARAMETER.page)),
    asset,
    adding: asset === null && params.get(ASSET_PARAMETER.add) === ADDING_A_UNIT,
  }
}

/** Write what the register shows as an address. A filter not applied, the
 *  first page and anything closed are left out. */
export function writeAssetFilters(filters: AssetFilters): URLSearchParams {
  const written = new URLSearchParams()
  if (filters.q !== null) written.set(ASSET_PARAMETER.q, filters.q)
  if (filters.branchCode !== null) written.set(ASSET_PARAMETER.branchCode, filters.branchCode)
  if (filters.status !== null) written.set(ASSET_PARAMETER.status, filters.status)
  if (filters.modelId !== null) written.set(ASSET_PARAMETER.modelId, filters.modelId)
  if (filters.page > FIRST_PAGE) written.set(ASSET_PARAMETER.page, String(filters.page))
  if (filters.asset !== null) written.set(ASSET_PARAMETER.asset, filters.asset)
  else if (filters.adding) written.set(ASSET_PARAMETER.add, ADDING_A_UNIT)
  return written
}

/** Whether the register is narrowed at all, the page and what is open aside. */
export function assetsAreFiltered(filters: AssetFilters): boolean {
  return filters.q !== null || filters.branchCode !== null || filters.status !== null || filters.modelId !== null
}

/** The query for one page of the register. */
export function assetQueryFor(filters: AssetFilters): AdminAssetQuery {
  return {
    q: filters.q ?? undefined,
    branchCode: filters.branchCode ?? undefined,
    status: filters.status ?? undefined,
    modelId: filters.modelId ?? undefined,
    page: filters.page,
    pageSize: ASSET_PAGE_SIZE,
  }
}

/** The id of the link that opens a unit from the list, so focus can come back
 *  to it when the unit is closed. */
export function openUnitLinkId(tag: string): string {
  return `open-unit-${tag}`
}

/** The address of the register with one unit open and the filters kept. */
export function unitHref(filters: AssetFilters, tag: string): string {
  return `${ASSET_REGISTER_PATH}?${writeAssetFilters({ ...filters, asset: tag, adding: false }).toString()}`
}
