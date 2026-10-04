/**
 * The category form of SC-20, and the bodies it is sent as.
 *
 * Every field carries the name the API gives it, so a message the API sends
 * about a field lands under that field. The rules about codes, slugs and
 * duplicates are the server's. The form only checks that the place in the
 * list is a whole number, which it needs to write a body at all.
 *
 * Nesting stops at two levels. So the parent a category may be put under is
 * offered from the top level categories only, and never the category itself.
 * The server holds the same rule and has the last word, so a category that
 * already has categories under it is refused by the server, under the parent.
 */

import type {
  AdminCategory,
  CategoryChangesRequest,
  NewCategoryRequest,
} from '../../shared/api/contract'

/** What the owner is typing. An empty parent means a top level category. */
export interface CategoryDraft {
  code: string
  name: string
  slug: string
  description: string
  parentCategoryId: string
  sortOrder: string
}

export type CategoryField = keyof CategoryDraft
export type CategoryDraftErrors = Partial<Record<CategoryField, string>>

/** Reading order of the form, which is also the order problems are listed in. */
export const CATEGORY_FIELD_ORDER: readonly CategoryField[] = [
  'name',
  'code',
  'slug',
  'parentCategoryId',
  'sortOrder',
  'description',
]

/** The value of the parent menu for a category at the top level. */
export const TOP_LEVEL = ''

/** Where a new category sorts until the owner says otherwise. */
const FIRST_PLACE = '0'

const WHOLE_NUMBER = /^\d+$/

const WHOLE_PLACE = 'Enter a whole number, for example 10. Lower numbers come first.'

/** A new category, at the top level, first among its siblings. */
export const EMPTY_CATEGORY_DRAFT: CategoryDraft = {
  code: '',
  name: '',
  slug: '',
  description: '',
  parentCategoryId: TOP_LEVEL,
  sortOrder: FIRST_PLACE,
}

/** The form for a category that exists, holding what the server holds. */
export function draftOfCategory(category: AdminCategory): CategoryDraft {
  return {
    code: category.code,
    name: category.name,
    slug: category.slug,
    description: category.description ?? '',
    parentCategoryId: category.parentCategoryId ?? TOP_LEVEL,
    sortOrder: String(category.sortOrder),
  }
}

/**
 * The categories a category may be put under. The top level ones, each parent
 * before its children the way the server lists them, and never the category
 * being changed.
 *
 * @param editingId The key of the category being changed, or null for a new one.
 */
export function parentChoices(categories: readonly AdminCategory[], editingId: string | null): AdminCategory[] {
  return categories.filter((category) => category.parentCategoryId === null && category.id !== editingId)
}

function optionalText(typed: string): string | null {
  const trimmed = typed.trim()
  return trimmed === '' ? null : trimmed
}

function placeOf(typed: string): number | null {
  const trimmed = typed.trim()
  return WHOLE_NUMBER.test(trimmed) ? Number(trimmed) : null
}

/** Either the body to send, or why the form cannot be written as one yet. */
export type CheckedCategory<Body> = { body: Body; errors: null } | { body: null; errors: CategoryDraftErrors }

/** The body of a new category, with every field the route takes. */
export function newCategoryRequestFrom(draft: CategoryDraft): CheckedCategory<NewCategoryRequest> {
  const sortOrder = placeOf(draft.sortOrder)
  if (sortOrder === null) return { body: null, errors: { sortOrder: WHOLE_PLACE } }
  return {
    errors: null,
    body: {
      code: draft.code.trim(),
      name: draft.name.trim(),
      slug: draft.slug.trim(),
      description: optionalText(draft.description),
      parentCategoryId: draft.parentCategoryId === TOP_LEVEL ? null : draft.parentCategoryId,
      sortOrder,
    },
  }
}

/** The body of a change, with only the fields that differ from what the server
 *  holds. An empty body means nothing was changed. */
export function categoryChangesFrom(
  category: AdminCategory,
  draft: CategoryDraft,
): CheckedCategory<CategoryChangesRequest> {
  const sortOrder = placeOf(draft.sortOrder)
  if (sortOrder === null) return { body: null, errors: { sortOrder: WHOLE_PLACE } }
  const changes: CategoryChangesRequest = {}
  for (const field of ['code', 'name', 'slug'] as const) {
    const typed = draft[field].trim()
    if (typed !== category[field]) changes[field] = typed
  }
  const description = optionalText(draft.description)
  if (description !== category.description) changes.description = description
  const parentCategoryId = draft.parentCategoryId === TOP_LEVEL ? null : draft.parentCategoryId
  if (parentCategoryId !== category.parentCategoryId) changes.parentCategoryId = parentCategoryId
  if (sortOrder !== category.sortOrder) changes.sortOrder = sortOrder
  return { body: changes, errors: null }
}
