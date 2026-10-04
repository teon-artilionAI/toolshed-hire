/**
 * What SC-20 shows, read from the address and written back to it.
 *
 * The search, the category, whether the models are published and the page
 * live in the address under the names the API takes, so a reload or a shared
 * link shows the same models. The model open in the form is there too, as
 * `model`, which holds its key or `new` for one being added, so a reload
 * keeps the form open.
 *
 * A filter the address names is passed to the server as it stands, apart from
 * a published value that is neither true nor false and a page that is not a
 * whole number from one, which are left out. Whether a filter makes sense is
 * the server's to say, with a 422 that the screen puts under the control.
 */

import { CATALOGUE_PAGE_SIZE } from '../../shared/api/admin-catalogue'
import type { AdminModelQuery } from '../../shared/api/contract'
import { FIRST_PAGE } from './report-address'

/** The names the catalogue keeps in the address. */
export const CATALOGUE_PARAMETER = {
  q: 'q',
  categoryId: 'categoryId',
  published: 'published',
  page: 'page',
  model: 'model',
} as const

/** The value of `model` while a new model is being added. */
export const NEW_MODEL = 'new'

/** The words the address and the API use for the two published filters. */
const PUBLISHED_WORD = { yes: 'true', no: 'false' } as const

/** What the list shows, and which model the form has open. A filter that is
 *  null is not applied. */
export interface CatalogueFilters {
  q: string | null
  categoryId: string | null
  published: boolean | null
  page: number
  /** The key of the model open in the form, `new` for one being added, or
   *  null when the form is closed. */
  model: string | null
}

/** The list with no filter, from its first page, and the form closed. */
export const NO_CATALOGUE_FILTERS: CatalogueFilters = {
  q: null,
  categoryId: null,
  published: null,
  page: FIRST_PAGE,
  model: null,
}

function readFilter(value: string | null): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

function readPublished(value: string | null): boolean | null {
  if (value === PUBLISHED_WORD.yes) return true
  if (value === PUBLISHED_WORD.no) return false
  return null
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

/** Read what the list shows from the address. */
export function readCatalogueFilters(params: URLSearchParams): CatalogueFilters {
  return {
    q: readFilter(params.get(CATALOGUE_PARAMETER.q)),
    categoryId: readFilter(params.get(CATALOGUE_PARAMETER.categoryId)),
    published: readPublished(params.get(CATALOGUE_PARAMETER.published)),
    page: readPage(params.get(CATALOGUE_PARAMETER.page)),
    model: readFilter(params.get(CATALOGUE_PARAMETER.model)),
  }
}

/** Write what the list shows as an address. A filter not applied, the first
 *  page and a closed form are left out. */
export function writeCatalogueFilters(filters: CatalogueFilters): URLSearchParams {
  const written = new URLSearchParams()
  if (filters.q !== null) written.set(CATALOGUE_PARAMETER.q, filters.q)
  if (filters.categoryId !== null) written.set(CATALOGUE_PARAMETER.categoryId, filters.categoryId)
  if (filters.published !== null) {
    written.set(CATALOGUE_PARAMETER.published, filters.published ? PUBLISHED_WORD.yes : PUBLISHED_WORD.no)
  }
  if (filters.page > FIRST_PAGE) written.set(CATALOGUE_PARAMETER.page, String(filters.page))
  if (filters.model !== null) written.set(CATALOGUE_PARAMETER.model, filters.model)
  return written
}

/** Whether the list is narrowed at all, the page and the form aside. */
export function catalogueIsFiltered(filters: CatalogueFilters): boolean {
  return filters.q !== null || filters.categoryId !== null || filters.published !== null
}

/** The query for one page of the models. */
export function modelQueryFor(filters: CatalogueFilters): AdminModelQuery {
  return {
    q: filters.q ?? undefined,
    categoryId: filters.categoryId ?? undefined,
    published: filters.published ?? undefined,
    page: filters.page,
    pageSize: CATALOGUE_PAGE_SIZE,
  }
}
