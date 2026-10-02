/**
 * The results half of SC-02.
 *
 * It draws one of five things. A prompt while a date is missing, a skeleton
 * while the search runs, the refusal when the API will not search those dates,
 * the shared error state when the search fails some other way, or the list
 * with its page controls.
 *
 * The line above the list is a live status. It announces that a search is
 * running and then how many models matched, so a person who cannot see the
 * list change still hears that it did.
 *
 * A search with a branch chosen is a narrower search and not the same list
 * with one branch picked out. The API then sends only the models that are free
 * at that branch, so the status line says "free at" and names the branch.
 */

import { useRef } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import type { AvailabilityPage } from '../../shared/api/contract'
import { HTTP_UNPROCESSABLE } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { isApiError } from '../../shared/api-problem'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { modelDetailHref } from './catalogue-links'
import { FIRST_PAGE } from './search-filters'
import type { SearchFilters } from './search-filters'
import SearchResultRow from './search-result-row'

/** Skeleton rows to draw while a search runs. */
const RESULT_SKELETON_COUNT = 4

function statusLine(
  phase: ReturnType<typeof queryPhase>,
  data: AvailabilityPage | undefined,
  branchName: string | null,
): string {
  if (phase === 'idle') return 'Waiting on a usable pair of dates.'
  if (phase === 'loading') return 'Checking what is free for your dates.'
  if (phase === 'failed' || !data) return 'The search did not finish.'
  const one = data.total === 1
  const days = `${data.hireDays} ${data.hireDays === 1 ? 'day' : 'days'}`
  const found = branchName
    ? `${data.total} ${one ? 'model is' : 'models are'} free at ${branchName} for ${days}.`
    : `${data.total} ${one ? 'model matches' : 'models match'}, across every branch, for ${days}.`
  const first = (data.page - 1) * data.pageSize + 1
  const last = first + data.items.length - 1
  const showing =
    data.items.length > 0 && data.total > data.items.length ? ` Showing ${first} to ${last}.` : ''
  return `${found}${showing}`
}

export default function SearchResultList({
  availability,
  filters,
  branchName,
  otherMessages,
  onChange,
  onClear,
}: {
  availability: UseQueryResult<AvailabilityPage>
  filters: SearchFilters
  /** The branch the search was narrowed to, or null when it looked at every
   *  branch. The list then holds only what is free at that branch. */
  branchName: string | null
  /** Refusals from the API that belong to no field on the form. */
  otherMessages: string[]
  onChange: (changes: Partial<SearchFilters>) => void
  onClear: () => void
}) {
  const regionRef = useRef<HTMLElement>(null)
  const phase = queryPhase(availability)
  const data = availability.data
  const refused =
    phase === 'failed' &&
    isApiError(availability.error) &&
    availability.error.status === HTTP_UNPROCESSABLE

  function goToPage(page: number) {
    onChange({ page })
    // The new page replaces the list, so I move focus back to the top of the
    // results. A keyboard user then reads the new page from its first row.
    regionRef.current?.focus()
  }

  return (
    <section ref={regionRef} tabIndex={-1} aria-label="Search results">
      <p className="mb-md text-sm text-slate-soft" role="status">
        {statusLine(phase, data, branchName)}
      </p>

      {phase === 'idle' && (
        <Notice tone="error" title="We cannot search these dates">
          Choose a collection date and a return date above.
        </Notice>
      )}

      {phase === 'loading' && <LoadingState shape="rows" count={RESULT_SKELETON_COUNT} />}

      {refused && (
        <Notice tone="error" title="We cannot search with those details">
          <p>Check the messages under the fields above and change what they point to.</p>
          {otherMessages.length > 0 && (
            <ul className="mt-xs list-disc pl-lg">
              {otherMessages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
        </Notice>
      )}

      {phase === 'failed' && !refused && (
        <ErrorState
          what="what is free for your dates"
          error={availability.error}
          onRetry={() => void availability.refetch()}
        />
      )}

      {phase === 'ready' && data && data.items.length === 0 && (
        <div className="card">
          {data.total > 0 && filters.page > FIRST_PAGE ? (
            <EmptyState
              title="That page is past the end of the results"
              body="The search has fewer pages than the address asked for."
              action={
                <button
                  type="button"
                  className="btn-secondary px-md"
                  onClick={() => goToPage(FIRST_PAGE)}
                >
                  Go to the first page
                </button>
              }
            />
          ) : (
            <EmptyState
              title={
                branchName
                  ? `Nothing in that search is free at ${branchName}`
                  : 'Nothing matches that search'
              }
              body="Try a wider category, another branch or a different pair of dates."
              action={
                <button type="button" className="btn-secondary px-md" onClick={onClear}>
                  <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Clear the filters
                </button>
              }
            />
          )}
        </div>
      )}

      {phase === 'ready' && data && data.items.length > 0 && (
        <>
          <ul className="flex flex-col gap-md" aria-busy={availability.isFetching}>
            {data.items.map((row) => (
              <SearchResultRow
                key={row.model.sku}
                row={row}
                hireDays={data.hireDays}
                detailHref={modelDetailHref(
                  row.model.slug,
                  { from: filters.from, to: filters.to },
                  filters.branch || undefined,
                )}
              />
            ))}
          </ul>
          <Pagination
            label="Search result pages"
            page={data.page}
            pageSize={data.pageSize}
            total={data.total}
            onPageChange={goToPage}
          />
        </>
      )}
    </section>
  )
}
