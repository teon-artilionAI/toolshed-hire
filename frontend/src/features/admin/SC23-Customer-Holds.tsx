/**
 * The customer holds view of SC-23.
 *
 * One page at a time from `GET /api/admin/customers`, filtered by standing and
 * by a search for a name, a phone number or an email address. The standing,
 * the search and the page live in the address, read and written by
 * users-address.ts. A change of standing is one request, so it applies as it
 * is chosen, and the search asks a moment after the last key.
 *
 * Each customer can be moved to either standing they are not in, with a
 * reason, from CustomerEntry. Once the server has answered, a notice above the
 * list says what was done and takes focus, because the customer may no longer
 * match the filter and leave the list. The list has the shared loading,
 * failed and empty states, and a refused filter shows its message under the
 * control.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ACCOUNT_STATUSES } from '../../shared/api/account'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AccountStatus, CustomerPage, CustomerSummary } from '../../shared/api/contract'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { EmptyState, Notice } from '../../shared/ui'
import { ACCOUNT_STANDING_LABEL, countOf } from '../counter/counter-labels'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { FIRST_PAGE } from './report-address'
import { CustomerEntry } from './SC23-Customer-Entry'
import { standingMoveWords } from './staff-words'
import { HOLD_FILTER_FIELDS, holdQueryFor, readHoldFilters, writeHoldFilters } from './users-address'
import type { HoldFilters } from './users-address'
import { useBranchList } from './use-branch-list'
import { useSearchDraft } from './use-search-draft'

const EVERY = ''
const SKELETON_ROWS = 3

const STANDING_OPTIONS = [
  { value: EVERY, label: 'Every standing' },
  ...ACCOUNT_STATUSES.map((status) => ({ value: status, label: ACCOUNT_STANDING_LABEL[status] })),
]

interface Outcome {
  title: string
  line: string
}

function statusLine(page: CustomerPage, filters: HoldFilters): string {
  const which = filters.status === null ? '' : `, ${ACCOUNT_STANDING_LABEL[filters.status].toLowerCase()}`
  return `${countOf(page.total, 'customer', 'customers')}${which}.`
}

function Customers({
  page,
  filters,
  branchName,
  onPage,
  onEvery,
  onMoved,
}: {
  page: CustomerPage
  filters: HoldFilters
  branchName: (code: string) => string
  onPage: (page: number) => void
  onEvery: () => void
  onMoved: (customer: CustomerSummary, to: AccountStatus) => void
}) {
  if (page.items.length === 0) {
    const pastTheEnd = page.total > 0
    const filtered = filters.status !== null || filters.q !== null
    return (
      <div className="card">
        <EmptyState
          title={pastTheEnd ? 'That page is past the end of the list' : filtered ? 'No customer matches' : 'There are no customers yet'}
          body={
            pastTheEnd
              ? 'Go back to the first page of the list.'
              : filters.status === 'ON_HOLD' && filters.q === null
                ? 'Nobody is on hold, so every customer may book.'
                : filtered
                  ? 'Nothing matches that standing and that search together. Show every customer to see the rest.'
                  : 'Customers appear here once they register or are registered at a counter.'
          }
          action={
            pastTheEnd ? (
              <button type="button" className="btn-secondary px-md" onClick={() => onPage(FIRST_PAGE)}>
                Go to the first page
              </button>
            ) : filtered ? (
              <button type="button" className="btn-secondary px-md" onClick={onEvery}>
                Show every customer
              </button>
            ) : undefined
          }
        />
      </div>
    )
  }
  return (
    <>
      <ol className="flex flex-col gap-md" aria-label="Customers">
        {page.items.map((customer) => (
          <li key={customer.id}>
            <CustomerEntry customer={customer} branchName={branchName} onMoved={onMoved} />
          </li>
        ))}
      </ol>
      <Pagination label="Customer pages" page={page.page} pageSize={page.pageSize} total={page.total} onPageChange={onPage} />
    </>
  )
}

export default function CustomerHolds() {
  const [params, setParams] = useSearchParams()
  const filters = readHoldFilters(params)
  const branches = useBranchList()
  const list = useQuery(adminQueries.customerHolds(holdQueryFor(filters)))
  const phase = queryPhase(list)
  const refused = phase === 'failed' && isRefusal(list.error)
  const fieldErrors = fieldErrorsFromProblem(list.error)
  const otherMessages = otherFieldMessages(fieldErrors, HOLD_FILTER_FIELDS)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)
  const regionRef = useRef<HTMLElement>(null)

  const show = useCallback(
    (changes: Partial<HoldFilters>) =>
      setParams((current) => writeHoldFilters({ ...readHoldFilters(current), page: FIRST_PAGE, ...changes }), { replace: true }),
    [setParams],
  )
  const search = useCallback((words: string | null) => show({ q: words }), [show])
  const [draft, setDraft] = useSearchDraft(filters.q, search)

  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  function goToPage(page: number) {
    show({ page })
    regionRef.current?.focus()
  }

  /** The words come from the customer as the server answered, so the count of
   *  bookings not collected is the one it kept. */
  function moved(customer: CustomerSummary, to: AccountStatus) {
    const words = standingMoveWords(customer, to)
    setOutcome({ title: words.outcome, line: words.outcomeLine })
  }

  return (
    <>
      {outcome !== null && (
        <div ref={outcomeRef} tabIndex={-1} className="mb-lg">
          <Notice tone="success" title={outcome.title}>
            <p>{outcome.line}</p>
          </Notice>
        </div>
      )}
      <form className="card mb-lg p-lg" aria-label="Choose which customers to show" onSubmit={(event) => event.preventDefault()}>
        <div className="grid gap-md sm:grid-cols-2">
          <SelectInput
            id="hold-standing"
            label="Standing"
            value={filters.status ?? EVERY}
            onChange={(value) => show({ status: ACCOUNT_STATUSES.find((status) => status === value) ?? null })}
            options={STANDING_OPTIONS}
            error={fieldErrors.status}
          />
          <TextInput
            id="hold-search"
            label="Search by name, phone or email"
            type="search"
            value={draft}
            onChange={setDraft}
            error={fieldErrors.q}
            autoComplete="off"
          />
        </div>
      </form>

      <section ref={regionRef} tabIndex={-1} aria-label="The customers">
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && list.data !== undefined
            ? statusLine(list.data, filters)
            : phase === 'loading'
              ? 'Loading the customers.'
              : refused
                ? 'The customers were not read for those filters.'
                : ''}
        </p>
        {refused ? (
          <Notice tone="error" title="The customers cannot be read with those filters">
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
          <ErrorState what="the customers" error={list.error} onRetry={() => void list.refetch()} />
        ) : list.data === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : (
          <div aria-busy={list.isFetching}>
            <Customers
              page={list.data}
              filters={filters}
              branchName={branches.nameOf}
              onPage={goToPage}
              onEvery={() => show({ status: null, q: null })}
              onMoved={moved}
            />
          </div>
        )}
      </section>
    </>
  )
}
