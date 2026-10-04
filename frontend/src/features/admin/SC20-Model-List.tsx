/**
 * The models on SC-20, with the search and the two filters above them.
 *
 * One page at a time from `GET /api/admin/models`, published or not. The
 * search, the category, whether a model is published and the page live in the
 * address under the names the API takes, so a reload or a shared link shows
 * the same models. The server does the searching, the filtering and the
 * paging. The search asks a moment after the last key, so it never asks on
 * every keystroke, and the two menus apply as they are chosen.
 *
 * It has the shared loading, failed and empty states. A refusal puts each of
 * the server's messages under the control it names, and lists any other.
 * Moving to another page moves focus to the top of the models.
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminCategory, AdminModel, AdminModelPage } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { countOf } from '../counter/counter-labels'
import { CATALOGUE_PARAMETER, catalogueIsFiltered, modelQueryFor } from './catalogue-address'
import type { CatalogueFilters } from './catalogue-address'
import { categoryOptionLabel } from './catalogue-labels'
import { FIRST_PAGE } from './report-address'
import ModelTable from './SC20-Model-Table'

/** How long the search waits after the last key before it asks. */
const SEARCH_DEBOUNCE_MS = 300

const SKELETON_ROWS = 3

const EVERY = ''

/** The filters that have a control on the screen, by the names the server gives them. */
const FILTER_FIELDS: readonly string[] = [
  CATALOGUE_PARAMETER.q,
  CATALOGUE_PARAMETER.categoryId,
  CATALOGUE_PARAMETER.published,
]

const PUBLISHED_OPTIONS = [
  { value: EVERY, label: 'Published and hidden' },
  { value: 'true', label: 'Published only' },
  { value: 'false', label: 'Hidden only' },
]

/** The change to the address a choice of the published menu makes. */
function publishedFrom(value: string): boolean | null {
  if (value === 'true') return true
  if (value === 'false') return false
  return null
}

function categoryOptions(categories: readonly AdminCategory[] | undefined, chosen: string | null) {
  const listed = (categories ?? []).map((category) => ({ value: category.id, label: categoryOptionLabel(category) }))
  const unknown =
    chosen !== null && !listed.some((option) => option.value === chosen)
      ? [{ value: chosen, label: 'The category in the address' }]
      : []
  return [{ value: EVERY, label: 'Every category' }, ...listed, ...unknown]
}

function Filters({
  filters,
  categories,
  categoriesFailed,
  retryCategories,
  fieldErrors,
  onShow,
}: {
  filters: CatalogueFilters
  categories: readonly AdminCategory[] | undefined
  categoriesFailed: boolean
  retryCategories: () => void
  fieldErrors: FieldErrors
  onShow: (changes: Partial<CatalogueFilters>) => void
}) {
  // The box holds what is being typed and the address holds what was last
  // searched. When the address changes from somewhere else, the box follows.
  const searched = filters.q ?? ''
  const [draft, setDraft] = useState(searched)
  const [lastSearched, setLastSearched] = useState(searched)
  if (searched !== lastSearched) {
    setLastSearched(searched)
    if (searched !== draft.trim()) setDraft(searched)
  }
  useEffect(() => {
    const typed = draft.trim()
    if (typed === searched) return
    const timer = window.setTimeout(() => onShow({ q: typed === '' ? null : typed, page: FIRST_PAGE }), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, searched, onShow])

  return (
    <form className="mb-md" aria-label="Find models" onSubmit={(event) => event.preventDefault()}>
      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <TextInput
          id="catalogue-search"
          label="Search by name or stock code"
          type="search"
          value={draft}
          onChange={setDraft}
          error={fieldErrors.q}
          autoComplete="off"
        />
        <SelectInput
          id="catalogue-category"
          label="Category"
          value={filters.categoryId ?? EVERY}
          onChange={(value) => onShow({ categoryId: value === EVERY ? null : value, page: FIRST_PAGE })}
          options={categoryOptions(categories, filters.categoryId)}
          error={fieldErrors.categoryId}
          help={categoriesFailed ? 'The categories could not be read, so only every category is offered.' : undefined}
        />
        <SelectInput
          id="catalogue-published"
          label="Shown to customers"
          value={filters.published === null ? EVERY : String(filters.published)}
          onChange={(value) => onShow({ published: publishedFrom(value), page: FIRST_PAGE })}
          options={PUBLISHED_OPTIONS}
          error={fieldErrors.published}
        />
      </div>
      {categoriesFailed && (
        <button type="button" className="btn-ghost mt-sm px-sm" onClick={retryCategories}>
          <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
          Read the categories again
        </button>
      )}
    </form>
  )
}

function Models({
  page,
  filtered,
  askingId,
  onPage,
  onClear,
  onAdd,
  onEdit,
  onAsk,
  onCancel,
  onPublication,
}: {
  page: AdminModelPage
  filtered: boolean
  askingId: string | null
  onPage: (page: number) => void
  onClear: () => void
  onAdd: () => void
  onEdit: (model: AdminModel) => void
  onAsk: (model: AdminModel) => void
  onCancel: () => void
  onPublication: (model: AdminModel, published: boolean) => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    return (
      <EmptyState
        title={pastTheEnd ? 'That page is past the end of the list' : filtered ? 'No model matches' : 'The catalogue has no models yet'}
        body={
          pastTheEnd
            ? 'Go back to the first page of the list.'
            : filtered
              ? 'Nothing matches that search and those filters together. Widen the search or clear the filters.'
              : 'Add the first model, then publish it once it is ready to be booked.'
        }
        action={
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={pastTheEnd ? () => onPage(FIRST_PAGE) : filtered ? onClear : onAdd}
          >
            {pastTheEnd ? 'Go to the first page' : filtered ? 'Clear the filters' : 'Add a model'}
          </button>
        }
      />
    )
  }
  return (
    <>
      <ModelTable
        models={page.items}
        askingId={askingId}
        onEdit={onEdit}
        onAsk={onAsk}
        onCancel={onCancel}
        onPublication={onPublication}
      />
      <Pagination label="Model pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function ModelList({
  filters,
  categories,
  categoriesFailed,
  retryCategories,
  onShow,
  onAdd,
  onEdit,
  onPublication,
}: {
  filters: CatalogueFilters
  categories: readonly AdminCategory[] | undefined
  categoriesFailed: boolean
  retryCategories: () => void
  /** Change what the address says. Changes not named keep their value. */
  onShow: (changes: Partial<CatalogueFilters>) => void
  onAdd: () => void
  onEdit: (model: AdminModel) => void
  onPublication: (model: AdminModel, published: boolean) => void
}) {
  const list = useQuery(adminQueries.models(modelQueryFor(filters)))
  const phase = queryPhase(list)
  const refused = phase === 'failed' && isRefusal(list.error)
  const fieldErrors = fieldErrorsFromProblem(list.error)
  const otherMessages = otherFieldMessages(fieldErrors, FILTER_FIELDS)
  const [askingId, setAskingId] = useState<string | null>(null)
  const regionRef = useRef<HTMLElement>(null)

  function goToPage(page: number) {
    onShow({ page })
    regionRef.current?.focus()
  }

  return (
    <>
      <Filters
        filters={filters}
        categories={categories}
        categoriesFailed={categoriesFailed}
        retryCategories={retryCategories}
        fieldErrors={fieldErrors}
        onShow={onShow}
      />
      <section ref={regionRef} tabIndex={-1} aria-label="The models">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && list.data !== undefined
            ? `${countOf(list.data.total, 'model matches', 'models match')}.`
            : phase === 'loading'
              ? 'Loading the models.'
              : refused
                ? 'The models were not read for those filters.'
                : ''}
        </p>
        {refused ? (
          <Notice tone="error" title="The list cannot be read with those filters">
            <p>Check the messages under the filters above and change what they point to.</p>
            {otherMessages.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {otherMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        ) : phase === 'failed' ? (
          <ErrorState what="the models" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={list.isFetching}>
            <Models
              page={list.data}
              filtered={catalogueIsFiltered(filters)}
              askingId={askingId}
              onPage={goToPage}
              onClear={() => onShow({ q: null, categoryId: null, published: null, page: FIRST_PAGE })}
              onAdd={onAdd}
              onEdit={onEdit}
              onAsk={(model) => setAskingId(model.id)}
              onCancel={() => setAskingId(null)}
              onPublication={(model, published) => {
                setAskingId(null)
                onPublication(model, published)
              }}
            />
          </div>
        )}
      </section>
    </>
  )
}
