/**
 * The public catalogue and availability endpoints.
 *
 * Six routes, none of which needs a sign in. Each function here makes one call
 * and reads the body into its contract type. The limits the contract states,
 * such as the largest page and the largest quantity, are named here so a screen
 * can build its controls from them without repeating a number.
 *
 * Nothing in an availability answer is a unit count. The API says whether a
 * branch can supply a model for the whole period, yes or no, and that is all a
 * customer is meant to know.
 */

import { api } from './client'
import type {
  AvailabilityPage,
  AvailabilityQuery,
  Branch,
  BranchAvailability,
  BranchList,
  Category,
  CategoryList,
  ModelAvailability,
  ModelAvailabilityQuery,
  ModelAvailabilityRow,
  ModelDetail,
  ModelListQuery,
  ModelPage,
  ModelSort,
  ModelSummary,
} from './contract'
import {
  readCount,
  readFlag,
  readList,
  readMoney,
  readNullableText,
  readObject,
  readText,
} from './read'

/** The page size the API uses when a request does not name one. */
export const DEFAULT_PAGE_SIZE = 24

/** The largest page the API will return. */
export const MAX_PAGE_SIZE = 50

/** The shortest text search the API accepts. */
export const MIN_SEARCH_LENGTH = 2

/** The fewest and the most units one availability question may ask about. */
export const MIN_QUANTITY = 1
export const MAX_QUANTITY = 10

/** The orders a model list can be asked for, in the order a menu shows them. */
export const MODEL_SORTS: readonly ModelSort[] = ['name', 'dailyRateAsc', 'dailyRateDesc']

/** The order the API uses when a request does not name one. */
export const DEFAULT_MODEL_SORT: ModelSort = 'name'

function readBranch(value: unknown, path: string): Branch {
  const record = readObject(value, path, 'a branch object')
  return {
    code: readText(record, 'code', path),
    name: readText(record, 'name', path),
    suburb: readText(record, 'suburb', path),
    city: readText(record, 'city', path),
    phone: readText(record, 'phone', path),
    opensAt: readText(record, 'opensAt', path),
    closesAt: readText(record, 'closesAt', path),
  }
}

function readCategory(value: unknown, path: string): Category {
  const record = readObject(value, path, 'a category object')
  return {
    code: readText(record, 'code', path),
    name: readText(record, 'name', path),
    slug: readText(record, 'slug', path),
    description: readText(record, 'description', path),
    parentCode: readNullableText(record, 'parentCode', path),
    sortOrder: readCount(record, 'sortOrder', path),
    modelCount: readCount(record, 'modelCount', path),
  }
}

function readModelSummary(value: unknown, path: string): ModelSummary {
  const record = readObject(value, path, 'a model object')
  return {
    sku: readText(record, 'sku', path),
    slug: readText(record, 'slug', path),
    name: readText(record, 'name', path),
    manufacturer: readText(record, 'manufacturer', path),
    modelNumber: readText(record, 'modelNumber', path),
    categoryCode: readText(record, 'categoryCode', path),
    categoryName: readText(record, 'categoryName', path),
    shortDescription: readText(record, 'shortDescription', path),
    dailyRate: readMoney(record, 'dailyRate', path),
    weeklyRate: readMoney(record, 'weeklyRate', path),
    depositAmount: readMoney(record, 'depositAmount', path),
    minHireDays: readCount(record, 'minHireDays', path),
    maxHireDays: readCount(record, 'maxHireDays', path),
    imagePath: readNullableText(record, 'imagePath', path),
  }
}

function readModelDetail(value: unknown, path: string): ModelDetail {
  const record = readObject(value, path, 'a model object')
  return {
    ...readModelSummary(record, path),
    longDescription: readNullableText(record, 'longDescription', path),
    lateFeePerDay: readMoney(record, 'lateFeePerDay', path),
  }
}

function readBranchAvailability(value: unknown, path: string): BranchAvailability {
  const record = readObject(value, path, 'a branch availability object')
  return {
    branchCode: readText(record, 'branchCode', path),
    branchName: readText(record, 'branchName', path),
    available: readFlag(record, 'available', path),
  }
}

function readAvailabilityRow(value: unknown, path: string): ModelAvailabilityRow {
  const record = readObject(value, path, 'an availability row')
  return {
    model: readModelSummary(record.model, path),
    branches: readList(record, 'branches', path, readBranchAvailability),
  }
}

function readBranchList(value: unknown, path: string): BranchList {
  const record = readObject(value, path, 'a list of branches')
  return { items: readList(record, 'items', path, readBranch) }
}

function readCategoryList(value: unknown, path: string): CategoryList {
  const record = readObject(value, path, 'a list of categories')
  return { items: readList(record, 'items', path, readCategory) }
}

function readModelPage(value: unknown, path: string): ModelPage {
  const record = readObject(value, path, 'a page of models')
  return {
    items: readList(record, 'items', path, readModelSummary),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

function readAvailabilityPage(value: unknown, path: string): AvailabilityPage {
  const record = readObject(value, path, 'a page of availability')
  return {
    from: readText(record, 'from', path),
    to: readText(record, 'to', path),
    hireDays: readCount(record, 'hireDays', path),
    items: readList(record, 'items', path, readAvailabilityRow),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

function readModelAvailability(value: unknown, path: string): ModelAvailability {
  const record = readObject(value, path, 'a model availability object')
  return {
    from: readText(record, 'from', path),
    to: readText(record, 'to', path),
    hireDays: readCount(record, 'hireDays', path),
    quantity: readCount(record, 'quantity', path),
    branches: readList(record, 'branches', path, readBranchAvailability),
  }
}

/** A slug is user input by the time it reaches here, so it is always encoded. */
function modelEndpoint(slug: string): string {
  return `/catalogue/models/${encodeURIComponent(slug)}`
}

/** GET /api/branches. */
export function listBranches(signal?: AbortSignal): Promise<BranchList> {
  return api.get('/branches', readBranchList, { signal })
}

/** GET /api/catalogue/categories. Parents arrive before their children. */
export function listCategories(signal?: AbortSignal): Promise<CategoryList> {
  return api.get('/catalogue/categories', readCategoryList, { signal })
}

/** GET /api/catalogue/models. */
export function listModels(query: ModelListQuery, signal?: AbortSignal): Promise<ModelPage> {
  return api.get('/catalogue/models', readModelPage, { query, signal })
}

/**
 * GET /api/catalogue/models/{slug}.
 *
 * @throws ApiError with status 404 when no model has that slug.
 */
export function getModel(slug: string, signal?: AbortSignal): Promise<ModelDetail> {
  return api.get(modelEndpoint(slug), readModelDetail, { signal })
}

/**
 * GET /api/catalogue/availability.
 *
 * @throws ApiError with status 422 when the dates or a filter are refused. The
 *   problem document then names each refused field under `errors`.
 */
export function searchAvailability(
  query: AvailabilityQuery,
  signal?: AbortSignal,
): Promise<AvailabilityPage> {
  return api.get('/catalogue/availability', readAvailabilityPage, { query, signal })
}

/**
 * GET /api/catalogue/models/{slug}/availability.
 *
 * @throws ApiError with status 404 for an unknown slug and 422 for dates or a
 *   quantity the API refuses.
 */
export function getModelAvailability(
  slug: string,
  query: ModelAvailabilityQuery,
  signal?: AbortSignal,
): Promise<ModelAvailability> {
  return api.get(`${modelEndpoint(slug)}/availability`, readModelAvailability, { query, signal })
}
