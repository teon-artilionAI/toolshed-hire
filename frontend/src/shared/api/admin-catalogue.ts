/**
 * The owner's catalogue. The categories and the product models, with their
 * rates, deposits, late fees and replacement values, and whether customers
 * see each model.
 *
 * Every route here is for an administrator, and the API refuses anyone else
 * with a 403. Each function makes one call and reads the body into its
 * contract type, checking every member, so a body that breaks the contract
 * fails here with the name of the field.
 *
 * Every rule about money, codes and nesting is the server's, and each refusal
 * comes back as a 422 naming its field. Nothing here checks a figure or works
 * one out. Nothing is ever deleted either. A category is switched off and a
 * model is hidden. Each write is sent once for each press of a button and
 * never repeated by the client, because a request that timed out may still
 * have reached the server.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  AdminCategory,
  AdminCategoryList,
  AdminModel,
  AdminModelPage,
  AdminModelQuery,
  CategoryChangesRequest,
  ModelChangesRequest,
  NewCategoryRequest,
  NewModelRequest,
  PublicationRequest,
} from './contract'
import {
  readCount,
  readFlag,
  readList,
  readMoney,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readText,
} from './read'

const CATEGORIES_ENDPOINT = '/admin/categories'
const MODELS_ENDPOINT = '/admin/models'

/** How many models a page of the owner's list holds. */
export const CATALOGUE_PAGE_SIZE = 20

/** An id is user input by the time it reaches here, so it is always encoded. */
function one(base: string, id: string): string {
  return `${base}/${encodeURIComponent(id)}`
}

function readAdminCategory(value: unknown, path: string): AdminCategory {
  const record = readObject(value, path, 'a category')
  return {
    id: readText(record, 'id', path),
    code: readText(record, 'code', path),
    name: readText(record, 'name', path),
    slug: readText(record, 'slug', path),
    description: readNullableText(record, 'description', path),
    parentCategoryId: readNullableText(record, 'parentCategoryId', path),
    parentName: readNullableText(record, 'parentName', path),
    sortOrder: readCount(record, 'sortOrder', path),
    isActive: readFlag(record, 'isActive', path),
    modelCount: readCount(record, 'modelCount', path),
  }
}

/** The moment a model last changed. The contract never sends it as null. */
function readChangedAt(record: Record<string, unknown>, path: string): string {
  const value = readNullableTimestamp(record, 'updatedAt', path)
  if (value === null) throw malformedResponse(path, `Expected field updatedAt from ${path} to be an instant, got null.`)
  return value
}

function readAdminModel(value: unknown, path: string): AdminModel {
  const record = readObject(value, path, 'a product model')
  return {
    id: readText(record, 'id', path),
    sku: readText(record, 'sku', path),
    name: readText(record, 'name', path),
    slug: readText(record, 'slug', path),
    categoryId: readText(record, 'categoryId', path),
    categoryName: readText(record, 'categoryName', path),
    manufacturer: readText(record, 'manufacturer', path),
    modelNumber: readText(record, 'modelNumber', path),
    shortDescription: readText(record, 'shortDescription', path),
    longDescription: readNullableText(record, 'longDescription', path),
    dailyRate: readMoney(record, 'dailyRate', path),
    weeklyRate: readMoney(record, 'weeklyRate', path),
    depositAmount: readMoney(record, 'depositAmount', path),
    lateFeePerDay: readMoney(record, 'lateFeePerDay', path),
    replacementValue: readMoney(record, 'replacementValue', path),
    minHireDays: readCount(record, 'minHireDays', path),
    maxHireDays: readCount(record, 'maxHireDays', path),
    isPublished: readFlag(record, 'isPublished', path),
    assetCount: readCount(record, 'assetCount', path),
    updatedAt: readChangedAt(record, path),
  }
}

function readPageMembers(record: Record<string, unknown>, path: string) {
  return {
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

function readCategoryList(value: unknown, path: string): AdminCategoryList {
  const record = readObject(value, path, 'the list of categories')
  return { items: readList(record, 'items', path, readAdminCategory), ...readPageMembers(record, path) }
}

function readModelPage(value: unknown, path: string): AdminModelPage {
  const record = readObject(value, path, 'a page of product models')
  return { items: readList(record, 'items', path, readAdminModel), ...readPageMembers(record, path) }
}

/**
 * The contract does not say what the publication route answers, so the screen
 * does not read it. It reads the list again, which shows the model as the
 * server now has it.
 */
function ignoreTheBody(): void {}

/**
 * GET /api/admin/categories. Every category, switched on or not, each parent
 * before its children.
 *
 * @throws ApiError with status 403 for anyone but an administrator.
 */
export function listAdminCategories(signal?: AbortSignal): Promise<AdminCategoryList> {
  return api.get(CATEGORIES_ENDPOINT, readCategoryList, { signal })
}

/**
 * POST /api/admin/categories. Answers 201 with the new category, switched on.
 *
 * @throws ApiError with status 422 naming the field the server refused, and
 *   403 for anyone but an administrator.
 */
export function createCategory(body: NewCategoryRequest): Promise<AdminCategory> {
  return api.post(CATEGORIES_ENDPOINT, body, readAdminCategory)
}

/**
 * PATCH /api/admin/categories/{id}. Changes the fields sent and leaves the rest.
 *
 * @throws ApiError with status 422 naming the field the server refused, 404
 *   when there is no such category, and 403 for anyone but an administrator.
 */
export function changeCategory(id: string, changes: CategoryChangesRequest): Promise<AdminCategory> {
  return api.patch(one(CATEGORIES_ENDPOINT, id), changes, readAdminCategory)
}

/**
 * GET /api/admin/models. One page of the models that match, published or not.
 *
 * @throws ApiError with status 422 naming a filter the server refused, and
 *   403 for anyone but an administrator.
 */
export function listAdminModels(query: AdminModelQuery, signal?: AbortSignal): Promise<AdminModelPage> {
  return api.get(MODELS_ENDPOINT, readModelPage, { query, signal })
}

/**
 * GET /api/admin/models/{id}. One model, published or not.
 *
 * @throws ApiError with status 404 when there is no such model, and 403 for
 *   anyone but an administrator.
 */
export function getAdminModel(id: string, signal?: AbortSignal): Promise<AdminModel> {
  return api.get(one(MODELS_ENDPOINT, id), readAdminModel, { signal })
}

/**
 * POST /api/admin/models. Answers 201 with the new model, which starts
 * unpublished.
 *
 * @throws ApiError with status 422 naming the field the server refused, and
 *   403 for anyone but an administrator.
 */
export function createModel(body: NewModelRequest): Promise<AdminModel> {
  return api.post(MODELS_ENDPOINT, body, readAdminModel)
}

/**
 * PATCH /api/admin/models/{id}. Changes the fields sent and leaves the rest. A
 * new figure reaches new bookings only, because every booking and hire keeps
 * its own copy.
 *
 * @throws ApiError with status 422 naming the field the server refused, 404
 *   when there is no such model, and 403 for anyone but an administrator.
 */
export function changeModel(id: string, changes: ModelChangesRequest): Promise<AdminModel> {
  return api.patch(one(MODELS_ENDPOINT, id), changes, readAdminModel)
}

/**
 * POST /api/admin/models/{id}/publication. Shows the model to customers or
 * hides it from them.
 *
 * @throws ApiError with status 409 or 422 when the server refuses, 404 when
 *   there is no such model, and 403 for anyone but an administrator.
 */
export function setModelPublication(id: string, published: boolean): Promise<void> {
  const body: PublicationRequest = { published }
  return api.post(`${one(MODELS_ENDPOINT, id)}/publication`, body, ignoreTheBody)
}
