/**
 * The staff accounts on SC-23, with the search and the filters above them.
 *
 * One page at a time from `GET /api/admin/users`, deactivated accounts
 * included. The server does the searching, the filtering and the paging, and
 * the address says which page of which accounts is on the screen.
 *
 * It has the shared loading, failed and empty states. A refusal puts each of
 * the server's messages under the control it names, and lists any other.
 * Moving to another page moves focus to the top of the accounts.
 */

import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminUser, AdminUserPage } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { FIRST_PAGE } from './report-address'
import StaffFiltersForm from './SC23-Staff-Filters'
import StaffTable from './SC23-Staff-Table'
import { NO_STAFF_FILTERS, STAFF_FILTER_FIELDS, staffAreFiltered, staffQueryFor } from './users-address'
import type { StaffFilters } from './users-address'

const SKELETON_ROWS = 3

/** What the list needs from the view around it. */
export interface StaffListHandlers {
  onShow: (changes: Partial<StaffFilters>) => void
  onOpen: (user: AdminUser) => void
  onAdd: () => void
}

function Accounts({
  page,
  filters,
  signedInId,
  branchName,
  onPage,
  onOpen,
  onShow,
  onAdd,
}: Omit<StaffListHandlers, 'onShow'> & {
  page: AdminUserPage
  filters: StaffFilters
  signedInId: string | null
  branchName: (code: string) => string
  onPage: (page: number) => void
  onShow: (changes: Partial<StaffFilters>) => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    const filtered = staffAreFiltered(filters)
    return (
      <EmptyState
        title={pastTheEnd ? 'That page is past the end of the list' : filtered ? 'No staff account matches' : 'There are no staff accounts yet'}
        body={
          pastTheEnd
            ? 'Go back to the first page of the list.'
            : filtered
              ? 'Nothing matches that search and those filters together. Widen the search or clear the filters.'
              : 'Add the first member of staff, and they choose their own password from a link.'
        }
        action={
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={pastTheEnd ? () => onPage(FIRST_PAGE) : filtered ? () => onShow(NO_STAFF_FILTERS) : onAdd}
          >
            {pastTheEnd ? 'Go to the first page' : filtered ? 'Clear the filters' : 'Add a staff account'}
          </button>
        }
      />
    )
  }
  return (
    <>
      <StaffTable accounts={page.items} signedInId={signedInId} branchName={branchName} onOpen={onOpen} />
      <Pagination label="Staff account pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function StaffList({
  filters,
  signedInId,
  branchName,
  ...handlers
}: StaffListHandlers & {
  filters: StaffFilters
  signedInId: string | null
  branchName: (code: string) => string
}) {
  const list = useQuery(adminQueries.staff(staffQueryFor(filters)))
  const phase = queryPhase(list)
  const refused = phase === 'failed' && isRefusal(list.error)
  const fieldErrors = fieldErrorsFromProblem(list.error)
  const otherMessages = otherFieldMessages(fieldErrors, STAFF_FILTER_FIELDS)
  const regionRef = useRef<HTMLElement>(null)

  function goToPage(page: number) {
    handlers.onShow({ page })
    regionRef.current?.focus()
  }

  return (
    <>
      <StaffFiltersForm filters={filters} fieldErrors={fieldErrors} onShow={handlers.onShow} />
      <section ref={regionRef} tabIndex={-1} aria-label="The staff accounts">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && list.data !== undefined
            ? `${countOf(list.data.total, 'account matches', 'accounts match')}.`
            : phase === 'loading'
              ? 'Loading the staff accounts.'
              : refused
                ? 'The staff accounts were not read for those filters.'
                : ''}
        </p>
        {refused ? (
          <Notice tone="error" title="The staff accounts cannot be read with those filters">
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
          <ErrorState what="the staff accounts" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={list.isFetching}>
            <Accounts
              page={list.data}
              filters={filters}
              signedInId={signedInId}
              branchName={branchName}
              onPage={goToPage}
              {...handlers}
            />
          </div>
        )}
      </section>
    </>
  )
}
