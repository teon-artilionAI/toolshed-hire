/**
 * The customers who match a search, on SC-12.
 *
 * The list is the server's. It matches the name, the phone number and the
 * email address at once, puts the best match first, and decides what a page
 * holds. Nothing is asked until two characters have been typed.
 *
 * Each customer is drawn as a block of their own, not a row of columns, so a
 * phone held at the counter never has to scroll sideways. Each says who it is,
 * how the account stands, and whether there is a login, and offers a booking
 * when the account may book. An account that may not says why, and offers
 * none.
 *
 * The line above the list is a polite status. It says that the search is
 * running and then how many matched, so a person who cannot see the list
 * change still hears that it did.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarPlus, ListChecks } from 'lucide-react'
import type { CustomerPage, CustomerSummary } from '../../shared/api/contract'
import { customerQueries } from '../../shared/api/counter-queries'
import { MIN_CUSTOMER_SEARCH_LENGTH } from '../../shared/api/customers'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, StatusPill } from '../../shared/ui'
import {
  ACCOUNT_STANDING_LABEL,
  ACCOUNT_STANDING_PILL,
  ID_DOCUMENT_LABEL,
  NO_BOOKING_BECAUSE,
  canBookFor,
} from './counter-labels'
import { bookingHref } from './counter-links'

/** How many customers a page of results holds. Few enough to read at a glance. */
export const CUSTOMER_PAGE_SIZE = 10

/** Pages are counted from one. */
export const FIRST_PAGE = 1

/** Skeleton blocks to draw while a search runs. */
const RESULT_SKELETON_COUNT = 3

function statusLine(phase: QueryPhase, searched: string, data: CustomerPage | undefined): string {
  if (searched.length < MIN_CUSTOMER_SEARCH_LENGTH) {
    return `Type ${MIN_CUSTOMER_SEARCH_LENGTH} characters or more to search.`
  }
  if (phase === 'loading') return 'Searching for customers.'
  if (phase !== 'ready' || !data) return 'The search did not work.'
  if (data.total === 0) return `Nobody on file matches "${searched}".`
  const count = `${data.total} ${data.total === 1 ? 'customer matches' : 'customers match'}`
  return `${count} "${searched}". The best match is first.`
}

function CustomerRow({
  customer,
  onChoose,
}: {
  customer: CustomerSummary
  onChoose: (customer: CustomerSummary) => void
}) {
  const status = customer.accountStatus
  return (
    <li className="rounded border border-line bg-surface p-md">
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div className="min-w-0">
          <p className="break-words font-medium text-ink">{customer.displayName}</p>
          {customer.companyName && (
            <p className="break-words text-sm text-slate-soft">{customer.companyName}</p>
          )}
          <p className="tabular mt-xs text-sm text-ink">{customer.phone}</p>
          <p className="break-all text-sm text-slate-soft">{customer.email ?? 'No email on file'}</p>
          <p className="text-sm text-slate-soft">
            {customer.billingSuburb}, {customer.billingCity}. {ID_DOCUMENT_LABEL[customer.idDocumentType]}{' '}
            ending {customer.idDocumentLast4}.
          </p>
          <div className="mt-sm flex flex-wrap gap-xs">
            <StatusPill status={ACCOUNT_STANDING_PILL[status]} label={ACCOUNT_STANDING_LABEL[status]} />
            <StatusPill
              status={customer.hasLogin ? 'CONFIRMED' : 'DRAFT'}
              label={customer.hasLogin ? 'Has a login' : 'No login'}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-sm">
          <button type="button" className="btn-secondary px-md" onClick={() => onChoose(customer)}>
            <ListChecks className="h-4 w-4 shrink-0" aria-hidden="true" />
            Show bookings{' '}
            <span className="sr-only">for {customer.displayName}</span>
          </button>
          {canBookFor(status) && (
            <Link to={bookingHref(customer.id)} className="btn-primary px-md">
              <CalendarPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
              New booking{' '}
              <span className="sr-only">for {customer.displayName}</span>
            </Link>
          )}
        </div>
      </div>
      {!canBookFor(status) && (
        <p className="mt-sm text-sm font-medium text-status-overdue">{NO_BOOKING_BECAUSE[status]}</p>
      )}
    </li>
  )
}

export function SearchResults({
  searched,
  page,
  regionRef,
  onPage,
  onChoose,
  onRegister,
}: {
  /** What was last searched for, trimmed. */
  searched: string
  page: number
  regionRef: RefObject<HTMLElement | null>
  onPage: (page: number) => void
  onChoose: (customer: CustomerSummary) => void
  /** Takes the person to the walk in form. */
  onRegister: () => void
}) {
  const searchable = searched.length >= MIN_CUSTOMER_SEARCH_LENGTH
  const results = useQuery({
    ...customerQueries.search({ q: searched, page, pageSize: CUSTOMER_PAGE_SIZE }),
    enabled: searchable,
  })
  const phase = queryPhase(results)
  const data = results.data

  return (
    <section ref={regionRef} tabIndex={-1} aria-label="Customers found" className="mb-lg">
      <p className="mb-md text-sm text-slate-soft" role="status">
        {statusLine(phase, searched, data)}
      </p>

      {searchable && phase === 'loading' && <LoadingState shape="rows" count={RESULT_SKELETON_COUNT} />}

      {searchable && phase === 'failed' && (
        <ErrorState what="the customers" error={results.error} onRetry={() => void results.refetch()} />
      )}

      {searchable && phase === 'ready' && data && data.items.length === 0 && (
        <div className="card">
          <EmptyState
            title={data.total > 0 ? 'That page is past the end of the results' : 'Nobody on file matches that'}
            body={
              data.total > 0
                ? 'Go back to the first page of the results.'
                : 'Check the spelling or the number for a slip, or register them as a walk in and carry on.'
            }
            action={
              data.total > 0 ? (
                <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                  Go to the first page
                </button>
              ) : (
                <button type="button" className="btn-primary px-md" onClick={onRegister}>
                  Register a walk in
                </button>
              )
            }
          />
        </div>
      )}

      {searchable && phase === 'ready' && data && data.items.length > 0 && (
        <div aria-busy={results.isFetching}>
          <ul className="flex flex-col gap-sm">
            {data.items.map((customer) => (
              <CustomerRow key={customer.id} customer={customer} onChoose={onChoose} />
            ))}
          </ul>
          <Pagination
            label="Customer result pages"
            page={data.page}
            pageSize={data.pageSize}
            total={data.total}
            onPageChange={onPage}
          />
        </div>
      )}
    </section>
  )
}
