/**
 * The owner's catalogue for tests, shaped the way the contract for the admin
 * catalogue describes it.
 *
 * Three categories, each parent before its children. Breaking and Drilling is
 * at the top level with Rotary Hammers under it, and Welding is at the top
 * level and switched off. Two models, one published and one hidden with no
 * units on the fleet.
 */

import type { AdminCategory, AdminCategoryList, AdminModel, AdminModelPage } from '../shared/api/contract'

export const CATEGORIES_ROUTE = 'GET /api/admin/categories'
export const CREATE_CATEGORY_ROUTE = 'POST /api/admin/categories'
export const MODELS_ROUTE = 'GET /api/admin/models'
export const CREATE_MODEL_ROUTE = 'POST /api/admin/models'

export function categoryRoute(id: string, method: 'PATCH' = 'PATCH'): string {
  return `${method} /api/admin/categories/${id}`
}

export function modelRoute(id: string, method: 'GET' | 'PATCH' = 'GET'): string {
  return `${method} /api/admin/models/${id}`
}

export function publicationRoute(id: string): string {
  return `POST /api/admin/models/${id}/publication`
}

export const BREAKING: AdminCategory = {
  id: 'ca700000-0000-4000-8000-000000000001',
  code: 'BREAK-DRILL',
  name: 'Breaking and Drilling',
  slug: 'breaking-drilling',
  description: 'Breakers, hammers and drills.',
  parentCategoryId: null,
  parentName: null,
  sortOrder: 10,
  isActive: true,
  modelCount: 0,
}

export const HAMMERS: AdminCategory = {
  id: 'ca700000-0000-4000-8000-000000000002',
  code: 'HAMMER',
  name: 'Rotary Hammers',
  slug: 'rotary-hammers',
  description: null,
  parentCategoryId: BREAKING.id,
  parentName: BREAKING.name,
  sortOrder: 11,
  isActive: true,
  modelCount: 2,
}

export const WELDING: AdminCategory = {
  id: 'ca700000-0000-4000-8000-000000000003',
  code: 'WELD',
  name: 'Welding',
  slug: 'welding',
  description: null,
  parentCategoryId: null,
  parentName: null,
  sortOrder: 40,
  isActive: false,
  modelCount: 0,
}

export function categoryList(items: AdminCategory[] = [BREAKING, HAMMERS, WELDING]): AdminCategoryList {
  return { items, page: 1, pageSize: 100, total: items.length }
}

export const HAMMER: AdminModel = {
  id: 'a0de1000-0000-4000-8000-000000000001',
  sku: 'DR-BOSCH-GBH226',
  name: 'Bosch GBH 2-26 DRE rotary hammer',
  slug: 'gbh-2-26-dre-rotary-hammer',
  categoryId: HAMMERS.id,
  categoryName: HAMMERS.name,
  manufacturer: 'Bosch',
  modelNumber: 'GBH 2-26 DRE',
  shortDescription: 'SDS-plus rotary hammer for drilling and light chiselling.',
  longDescription: null,
  dailyRate: '280.00',
  weeklyRate: '1120.00',
  depositAmount: '1500.00',
  lateFeePerDay: '50.00',
  replacementValue: '4200.00',
  minHireDays: 1,
  maxHireDays: 28,
  isPublished: true,
  assetCount: 6,
  updatedAt: '2026-03-11T15:30:00+02:00',
}

export const BREAKER: AdminModel = {
  ...HAMMER,
  id: 'a0de1000-0000-4000-8000-000000000002',
  sku: 'BR-HILTI-TE1000',
  name: 'Hilti TE 1000-AVR breaker',
  slug: 'te-1000-avr-breaker',
  manufacturer: 'Hilti',
  modelNumber: 'TE 1000-AVR',
  dailyRate: '620.00',
  weeklyRate: '2480.00',
  depositAmount: '2500.00',
  lateFeePerDay: '120.00',
  replacementValue: '18500.00',
  isPublished: false,
  assetCount: 0,
}

export function modelPage(items: AdminModel[] = [HAMMER, BREAKER], overrides: Partial<AdminModelPage> = {}): AdminModelPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
