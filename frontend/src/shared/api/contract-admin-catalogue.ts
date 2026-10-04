/**
 * The admin catalogue wire types. The categories and the product models as
 * the owner manages them, with the rates, the deposit, the late fee and the
 * replacement value of each model, and whether customers see it.
 *
 * These are written by hand from the contract for branch 019, because the
 * backend half of the change is built at the same time and the OpenAPI
 * document does not describe these routes yet. Once it does, `npm run
 * api:types` brings them into schema.d.ts and each type here is rebuilt from
 * the generated shapes, the way every other contract module is. Until then a
 * reader checks every member of every body, so a body that breaks the contract
 * still fails at the boundary with the name of the field.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { IsoTimestamp, Money } from './contract-kit'

/**
 * One category as the owner sees it, switched on or off.
 *
 * `parentCategoryId` and `parentName` are null for a top level category.
 * Nesting stops at two levels, so a parent never has a parent of its own.
 * `description` is null when the category has none. `modelCount` is the
 * number of models the category holds itself, published or not.
 */
export interface AdminCategory {
  id: string
  code: string
  name: string
  slug: string
  description: string | null
  parentCategoryId: string | null
  parentName: string | null
  sortOrder: number
  isActive: boolean
  modelCount: number
}

/** `GET /api/admin/categories`. Every category, switched on or not, each
 *  parent before its children. */
export interface AdminCategoryList {
  items: AdminCategory[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body `POST /api/admin/categories` accepts. A new category starts
 * switched on. A parent must itself be at the top level, and a code or a slug
 * already in use is refused, each with a 422 naming the field.
 */
export interface NewCategoryRequest {
  code: string
  name: string
  slug: string
  description: string | null
  parentCategoryId: string | null
  sortOrder: number
}

/** The body `PATCH /api/admin/categories/{id}` accepts. Any of the fields of a
 *  new category, and whether it is switched on. A field left out keeps its value. */
export type CategoryChangesRequest = Partial<NewCategoryRequest & { isActive: boolean }>

/**
 * One product model as the owner sees it, published or not.
 *
 * The rates are per unit and exclude VAT. `replacementValue` caps what a
 * damage charge for one unit can come to. `longDescription` is null when the
 * model has none. `assetCount` is how many units of it the fleet holds. Each
 * booking and hire keeps its own copy of the figures, so a change here never
 * reaches one already made.
 */
export interface AdminModel {
  id: string
  sku: string
  name: string
  slug: string
  categoryId: string
  categoryName: string
  manufacturer: string
  modelNumber: string
  shortDescription: string
  longDescription: string | null
  dailyRate: Money
  weeklyRate: Money
  depositAmount: Money
  lateFeePerDay: Money
  replacementValue: Money
  minHireDays: number
  maxHireDays: number
  isPublished: boolean
  assetCount: number
  updatedAt: IsoTimestamp
}

/**
 * The query `GET /api/admin/models` accepts.
 *
 * `q` is free text the server matches, such as part of a name or a stock
 * code. `published` true lists the published models only and false the hidden
 * ones only. Every filter may be left out. The screen always sends the
 * page and its size.
 */
export interface AdminModelQuery {
  q?: string
  categoryId?: string
  published?: boolean
  page: number
  pageSize: number
}

/** `GET /api/admin/models`. One page of the models that match. */
export interface AdminModelPage {
  items: AdminModel[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body `POST /api/admin/models` accepts. Every field of a model except the
 * ones the server keeps itself. A new model starts unpublished, so whether it
 * is published is not sent. The server refuses a stock code or a slug already
 * in use, money below zero, a weekly rate above seven days at the daily rate,
 * a shortest hire above the longest and a category that is switched off, each
 * with a 422 naming the field.
 */
export type NewModelRequest = Omit<AdminModel, 'id' | 'categoryName' | 'isPublished' | 'assetCount' | 'updatedAt'>

/** The body `PATCH /api/admin/models/{id}` accepts. Any field of a new model
 *  except the stock code, which never changes once the model exists. */
export type ModelChangesRequest = Partial<Omit<NewModelRequest, 'sku'>>

/** The body `POST /api/admin/models/{id}/publication` accepts. True shows the
 *  model to customers and false hides it. */
export interface PublicationRequest {
  published: boolean
}
