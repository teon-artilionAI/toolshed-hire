/**
 * SC-02 Availability Search Results.
 *
 * This is where the double booking problem is visibly solved. Every row
 * answers one question honestly. Can I have this one, at this branch, for
 * these exact days. The answer comes from the API for the period in the
 * address, and it is free or not free per branch, never a count.
 *
 * Choosing a branch narrows the list to the models that are free at that
 * branch. A parent category brings its children with it.
 *
 * The search lives in the address bar. The screen reads its filters from the
 * query string and changes them by writing a new one, so a counter assistant
 * can send a customer a link to the search they just ran, and a reload brings
 * the same search back.
 *
 * The API is the judge of the dates. A pair it will not search comes back as
 * a 422, and the message for each date is shown under its own field.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { SlidersHorizontal } from 'lucide-react'
import { MIN_SEARCH_LENGTH, MODEL_SORTS } from '../../shared/api/catalogue'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { Category, ModelSort } from '../../shared/api/contract'
import { fieldErrorsFromProblem, otherFieldMessages } from '../../shared/api/problem-fields'
import { Field, PageHeader } from '../../shared/ui'
import { todayInBranchTime } from '../../shared/today'
import { ANY_BRANCH, BranchSelect, PeriodFields } from './catalogue-ui'
import { describePeriod } from './hire-period'
import {
  FIRST_PAGE,
  availabilityQueryFor,
  readSearchFilters,
  writeSearchFilters,
} from './search-filters'
import type { SearchFilters } from './search-filters'
import SearchResultList from './SC02-Result-List'

/** How long the text search waits after the last keystroke before it runs. */
const SEARCH_DEBOUNCE_MS = 300

const EVERY_CATEGORY = ''

const SORT_LABEL: Record<ModelSort, string> = {
  name: 'Name, A to Z',
  dailyRateAsc: 'Daily rate, lowest first',
  dailyRateDesc: 'Daily rate, highest first',
}

/** The fields this form shows a message under. Anything else the API refuses
 *  is listed in the notice above the results. */
const FORM_FIELDS = ['from', 'to', 'q', 'category', 'branch', 'sort']

/** A child category is listed under its parent's name, so two children with
 *  similar names can be told apart in a flat menu. */
function categoryLabel(category: Category, all: Category[]): string {
  const parent = all.find((candidate) => candidate.code === category.parentCode)
  return parent ? `${parent.name}: ${category.name}` : category.name
}

export default function SearchResults() {
  const [params, setParams] = useSearchParams()
  const [today] = useState(() => todayInBranchTime())
  const filters = useMemo(() => readSearchFilters(params, today), [params, today])

  const update = useCallback(
    (changes: Partial<SearchFilters>) => {
      // Any change to what is searched starts again from the first page.
      const next = { ...filters, page: FIRST_PAGE, ...changes }
      setParams(writeSearchFilters(next), { replace: true })
    },
    [filters, setParams],
  )

  // Keep the address bar in step, so a bare /search gains its dates and the
  // search can be shared or bookmarked.
  useEffect(() => {
    const canonical = writeSearchFilters(filters)
    if (canonical.toString() !== params.toString()) setParams(canonical, { replace: true })
  }, [filters, params, setParams])

  // The text box holds what is being typed. The address holds what was last
  // searched. When the address changes from somewhere else, the box follows.
  const [queryDraft, setQueryDraft] = useState(filters.q)
  const [searchedQuery, setSearchedQuery] = useState(filters.q)
  if (filters.q !== searchedQuery) {
    setSearchedQuery(filters.q)
    if (filters.q !== queryDraft.trim()) setQueryDraft(filters.q)
  }
  useEffect(() => {
    const typed = queryDraft.trim()
    if (typed === filters.q) return
    const timer = window.setTimeout(() => update({ q: typed }), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [queryDraft, filters.q, update])

  const branches = useQuery(catalogueQueries.branches())
  const categories = useQuery(catalogueQueries.categories())
  const query = availabilityQueryFor(filters)
  const availability = useQuery({
    ...catalogueQueries.availability(query ?? { from: filters.from, to: filters.to }),
    enabled: query !== null,
  })

  const fieldErrors = fieldErrorsFromProblem(availability.error)
  const categoryItems = categories.data?.items ?? []
  const knownCategory =
    filters.category === EVERY_CATEGORY ||
    categoryItems.some((category) => category.slug === filters.category)
  // The name is on its way with the branch list. Until it is here the search
  // is still narrowed to that branch, so the status line must still say so.
  const branchName = filters.branch
    ? (branches.data?.items.find((branch) => branch.code === filters.branch)?.name ??
      'the chosen branch')
    : null
  const periodLabel = describePeriod(filters.from, filters.to)

  function clearFilters() {
    setQueryDraft('')
    update({ q: '', category: EVERY_CATEGORY, branch: '' })
  }

  return (
    <>
      <PageHeader
        screenId="SC-02"
        title="What is free for your dates"
        subtitle={`Answers are for the whole hire${periodLabel ? `, ${periodLabel}` : ''}. A tool only counts as free if it is free every day of the period.`}
      />

      <form
        className="card mb-lg p-lg"
        aria-label="Filter the catalogue"
        onSubmit={(e) => e.preventDefault()}
      >
        <h2 className="mb-md flex items-center gap-sm text-sm font-semibold uppercase tracking-wide text-slate-soft">
          <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden="true" />
          Narrow it down
        </h2>
        <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label="Search by tool or make"
            htmlFor="search-q"
            help={`Type ${MIN_SEARCH_LENGTH} letters or more. Fewer are not searched on.`}
            error={fieldErrors.q}
          >
            <input
              id="search-q"
              type="search"
              className="field-input"
              placeholder="Breaker, Bosch, mixer"
              value={queryDraft}
              aria-invalid={fieldErrors.q ? true : undefined}
              aria-describedby={fieldErrors.q ? 'search-q-help search-q-error' : 'search-q-help'}
              onChange={(e) => setQueryDraft(e.target.value)}
            />
          </Field>
          <Field label="Category" htmlFor="search-category" error={fieldErrors.category}>
            <select
              id="search-category"
              className="field-input cursor-pointer"
              value={filters.category}
              aria-invalid={fieldErrors.category ? true : undefined}
              aria-describedby={fieldErrors.category ? 'search-category-error' : undefined}
              onChange={(e) => update({ category: e.target.value })}
            >
              <option value={EVERY_CATEGORY}>Every category</option>
              {!knownCategory && <option value={filters.category}>Chosen category</option>}
              {categoryItems.map((category) => (
                <option key={category.code} value={category.slug}>
                  {categoryLabel(category, categoryItems)}
                </option>
              ))}
            </select>
          </Field>
          <BranchSelect
            id="search-branch"
            label="Branch"
            branches={branches.data?.items ?? []}
            value={filters.branch || ANY_BRANCH}
            onChange={(value) => update({ branch: value === ANY_BRANCH ? '' : value })}
            allLabel="Any branch"
            help="Choose one to list only what is free there."
            error={fieldErrors.branch}
          />
          <PeriodFields
            idPrefix="search"
            startIso={filters.from}
            endIso={filters.to}
            minIso={today}
            onChangeStart={(from) => update({ from })}
            onChangeEnd={(to) => update({ to })}
            startError={filters.from ? fieldErrors.from : 'Choose a collection date.'}
            endError={filters.to ? fieldErrors.to : 'Choose a return date.'}
          />
          <Field label="Sort by" htmlFor="search-sort" error={fieldErrors.sort}>
            <select
              id="search-sort"
              className="field-input cursor-pointer"
              value={filters.sort}
              aria-invalid={fieldErrors.sort ? true : undefined}
              aria-describedby={fieldErrors.sort ? 'search-sort-error' : undefined}
              onChange={(e) => {
                const sort = MODEL_SORTS.find((candidate) => candidate === e.target.value)
                if (sort) update({ sort })
              }}
            >
              {MODEL_SORTS.map((sort) => (
                <option key={sort} value={sort}>
                  {SORT_LABEL[sort]}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </form>

      <SearchResultList
        availability={availability}
        filters={filters}
        branchName={branchName}
        otherMessages={otherFieldMessages(fieldErrors, FORM_FIELDS)}
        onChange={update}
        onClear={clearFilters}
      />
    </>
  )
}
