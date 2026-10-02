/**
 * The SC-02 search, as the address bar holds it.
 *
 * The address is the one place the search lives. The screen reads its filters
 * from the query string on every render and changes them by writing a new
 * query string, so a reload, a bookmark or a link sent to a customer restores
 * exactly the search that was on the screen.
 *
 * A query string is user input. Nothing here trusts it. A sort or a page the
 * screen cannot offer falls back to the default. The dates, the category and
 * the branch are passed on as they are, because the API is the judge of those
 * and its refusal comes back with a message for the field.
 */

import {
  DEFAULT_MODEL_SORT,
  DEFAULT_PAGE_SIZE,
  MIN_SEARCH_LENGTH,
  MODEL_SORTS,
} from '../../shared/api/catalogue'
import type { AvailabilityQuery, ModelSort } from '../../shared/api/contract'
import { defaultPeriod } from './hire-period'

export const FIRST_PAGE = 1

export interface SearchFilters {
  /** Collection date. Empty when the customer has cleared the field. */
  from: string
  /** Return date. Empty when the customer has cleared the field. */
  to: string
  /** The text search, trimmed. Empty means no text search. */
  q: string
  /** A category slug. Empty means every category. */
  category: string
  /** A branch code. Empty means any branch. */
  branch: string
  sort: ModelSort
  /** Counted from 1. */
  page: number
}

function readSort(value: string | null): ModelSort {
  return MODEL_SORTS.find((sort) => sort === value) ?? DEFAULT_MODEL_SORT
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

/**
 * Read the search out of a query string.
 *
 * @param today Used for the dates a bare `/search` opens with.
 */
export function readSearchFilters(params: URLSearchParams, today: string): SearchFilters {
  const fallback = defaultPeriod(today)
  return {
    from: params.get('from') ?? fallback.startIso,
    to: params.get('to') ?? fallback.endIso,
    q: (params.get('q') ?? '').trim(),
    category: params.get('category') ?? '',
    branch: params.get('branch') ?? '',
    sort: readSort(params.get('sort')),
    page: readPage(params.get('page')),
  }
}

/**
 * Write the search as a query string.
 *
 * The dates are always written, even when empty, so a cleared date stays
 * cleared on a reload. Everything else is left out when it is at its default,
 * which keeps a shared link short.
 */
export function writeSearchFilters(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams({ from: filters.from, to: filters.to })
  if (filters.q) params.set('q', filters.q)
  if (filters.category) params.set('category', filters.category)
  if (filters.branch) params.set('branch', filters.branch)
  if (filters.sort !== DEFAULT_MODEL_SORT) params.set('sort', filters.sort)
  if (filters.page > FIRST_PAGE) params.set('page', String(filters.page))
  return params
}

/**
 * The question to put to the API for a search.
 *
 * @returns Null when a date is missing, because there is then nothing to ask.
 *   A text search shorter than the API accepts is left out and not sent.
 */
export function availabilityQueryFor(filters: SearchFilters): AvailabilityQuery | null {
  if (!filters.from || !filters.to) return null
  return {
    from: filters.from,
    to: filters.to,
    q: filters.q.length >= MIN_SEARCH_LENGTH ? filters.q : undefined,
    category: filters.category || undefined,
    branch: filters.branch || undefined,
    sort: filters.sort,
    page: filters.page,
    pageSize: DEFAULT_PAGE_SIZE,
  }
}
