/**
 * The words SC-20 uses for what the server sends about the catalogue.
 *
 * A status is always written in words beside its colour, so the pill is
 * chosen here with its label. The tone of a pill comes from the shared status
 * scale in ui.tsx.
 */

import type { AdminCategory } from '../../shared/api/contract'

/** A model customers can see, and one hidden from them. */
export const PUBLISHED_WORDS = 'Published'
export const HIDDEN_WORDS = 'Hidden'

/** A category in the catalogue, and one taken out of it. */
export const SWITCHED_ON_WORDS = 'Switched on'
export const SWITCHED_OFF_WORDS = 'Switched off'

/** The shared status whose tone a shown model or a category in use takes. */
const IN_USE_TONE = 'AVAILABLE'
/** The shared status whose tone a hidden model takes. */
const HIDDEN_TONE = 'DRAFT'
/** The shared status whose tone a category switched off takes. */
const SWITCHED_OFF_TONE = 'RETIRED'

/** The pill of a model, by whether customers see it. */
export function publicationPill(isPublished: boolean): { status: string; label: string } {
  return isPublished ? { status: IN_USE_TONE, label: PUBLISHED_WORDS } : { status: HIDDEN_TONE, label: HIDDEN_WORDS }
}

/** The pill of a category, by whether it is switched on. */
export function categoryPill(isActive: boolean): { status: string; label: string } {
  return isActive
    ? { status: IN_USE_TONE, label: SWITCHED_ON_WORDS }
    : { status: SWITCHED_OFF_TONE, label: SWITCHED_OFF_WORDS }
}

/** The id of the edit button of a model, so focus can come back to it when
 *  the form closes. */
export function editModelButtonId(modelId: string): string {
  return `edit-model-${modelId}`
}

/** How a category reads in a menu. A child names its parent, and one that is
 *  switched off says so. */
export function categoryOptionLabel(category: AdminCategory): string {
  const place = category.parentName === null ? category.name : `${category.name}, under ${category.parentName}`
  return category.isActive ? place : `${place} (switched off)`
}
