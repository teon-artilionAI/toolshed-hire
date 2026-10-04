/**
 * The register on SC-21, with the search and the filters above it.
 *
 * One page at a time from `GET /api/admin/assets`, retired units included. The
 * server does the searching, the filtering and the paging, and the address
 * says which page of which units is on the screen.
 *
 * It has the shared loading, failed and empty states. A refusal puts each of
 * the server's messages under the control it names, and lists any other.
 * Moving to another page moves focus to the top of the units.
 */

import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminAssetPage } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { ASSET_FILTER_FIELDS, assetQueryFor, assetsAreFiltered, unitHref } from './asset-address'
import type { AssetFilters as Filters } from './asset-address'
import { FIRST_PAGE } from './report-address'
import AssetFilters from './SC21-Asset-Filters'
import AssetTable from './SC21-Asset-Table'

const SKELETON_ROWS = 3

function Units({
  page,
  filters,
  onPage,
  onClear,
  onAdd,
}: {
  page: AdminAssetPage
  filters: Filters
  onPage: (page: number) => void
  onClear: () => void
  onAdd: () => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    const filtered = assetsAreFiltered(filters)
    return (
      <EmptyState
        title={pastTheEnd ? 'That page is past the end of the list' : filtered ? 'No unit matches' : 'The register has no units yet'}
        body={
          pastTheEnd
            ? 'Go back to the first page of the list.'
            : filtered
              ? 'Nothing matches that search and those filters together. Widen the search or clear the filters.'
              : 'Register the first unit, then commission it once it has been checked.'
        }
        action={
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={pastTheEnd ? () => onPage(FIRST_PAGE) : filtered ? onClear : onAdd}
          >
            {pastTheEnd ? 'Go to the first page' : filtered ? 'Clear the filters' : 'Register a unit'}
          </button>
        }
      />
    )
  }
  return (
    <>
      <AssetTable units={page.items} hrefOf={(tag) => unitHref(filters, tag)} />
      <Pagination label="Register pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function AssetList({
  filters,
  onShow,
  onAdd,
}: {
  filters: Filters
  /** Change what the address says. Changes not named keep their value. */
  onShow: (changes: Partial<Filters>) => void
  onAdd: () => void
}) {
  const list = useQuery(adminQueries.assets(assetQueryFor(filters)))
  const phase = queryPhase(list)
  const refused = phase === 'failed' && isRefusal(list.error)
  const fieldErrors = fieldErrorsFromProblem(list.error)
  const otherMessages = otherFieldMessages(fieldErrors, ASSET_FILTER_FIELDS)
  const regionRef = useRef<HTMLElement>(null)

  function goToPage(page: number) {
    onShow({ page })
    regionRef.current?.focus()
  }

  return (
    <>
      <AssetFilters filters={filters} fieldErrors={fieldErrors} onShow={onShow} />
      <section ref={regionRef} tabIndex={-1} aria-label="The units">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && list.data !== undefined
            ? `${countOf(list.data.total, 'unit matches', 'units match')}, in tag order.`
            : phase === 'loading'
              ? 'Loading the units.'
              : refused
                ? 'The units were not read for those filters.'
                : ''}
        </p>
        {refused ? (
          <Notice tone="error" title="The register cannot be read with those filters">
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
          <ErrorState what="the register" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={list.isFetching}>
            <Units
              page={list.data}
              filters={filters}
              onPage={goToPage}
              onClear={() => onShow({ q: null, branchCode: null, status: null, modelId: null, page: FIRST_PAGE })}
              onAdd={onAdd}
            />
          </div>
        )}
      </section>
    </>
  )
}
