/**
 * Catalogue lookups shared by SC-01 to SC-04.
 *
 * Separate from `catalogue-ui.tsx` so that file exports components only,
 * which keeps fast refresh working and keeps each file to one job. Nothing
 * here holds state or invents data; it reads the fixtures and answers the
 * three questions the customer screens keep asking: what do we hire, which
 * category is it in, and how many days is this hire.
 */

import {
  Container,
  Disc3,
  Hammer,
  Layers,
  MoveVertical,
  Trees,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { categories, productModels } from '../../shared/fixtures'
import type { Category, ProductModel, Uuid } from '../../shared/types'
import { daysBetween } from '../../shared/format'

/** One icon per category, so the tiles read at a glance on a phone. */
export const CATEGORY_ICON: Record<string, LucideIcon> = {
  'breaking-drilling': Hammer,
  compaction: Layers,
  'concrete-mixing': Container,
  'cutting-grinding': Disc3,
  'access-lifting': MoveVertical,
  gardening: Trees,
  'power-lighting': Zap,
}

/** A spanner rather than a hole, if a new category arrives without one. */
export function categoryIconFor(slug: string): LucideIcon {
  return CATEGORY_ICON[slug] ?? Wrench
}

/** Only published models are ever shown to a customer. */
export const catalogue: ProductModel[] = productModels.filter((m) => m.published)

export function categoryOf(model: ProductModel): Category | undefined {
  return categories.find((c) => c.id === model.categoryId)
}

/** Looks through every model, published or not, so an unpublished one can
 *  be told apart from an address that means nothing. */
export function modelById(id: Uuid): ProductModel | undefined {
  return productModels.find((m) => m.id === id)
}

export function modelsInCategory(categoryId: Uuid): ProductModel[] {
  return catalogue.filter((m) => m.categoryId === categoryId)
}

/**
 * Chargeable days in a hire period, matching the half open rule in the
 * schema. The 6th to the 10th is four days, and never fewer than one, so a
 * mistyped period cannot produce a free hire.
 */
export function hireDays(startIso: string, endIso: string): number {
  return Math.max(1, daysBetween(startIso, endIso))
}
