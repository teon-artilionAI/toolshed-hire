/**
 * SC-07 My Reservations.
 *
 * Everything the signed in customer has booked, newest first, read from the
 * API. The list is the server's. It decides whose bookings these are, their
 * order, and what a page holds, and it does the filtering by status.
 *
 * The filter and the page live in the address bar. The screen reads them from
 * the query string and changes them by writing a new one, so a reload or a
 * bookmark brings the same list back. A query string is user input, so a
 * status or a page the screen cannot offer falls back to all bookings and the
 * first page.
 *
 * A basket that was priced and never held is a reservation too, in the status
 * the customer reads as "Not finished". It is not a booking anybody made, so
 * the list leaves those out until the filter asks for them. The API filters by
 * one status or by none, so the screen asks for every status and leaves the
 * unfinished rows of the page out itself. It also asks how many unfinished
 * ones there are, so the count it gives is right and it can say that some were
 * left out. The pages are still the server's, so a page can show fewer rows
 * than it holds.
 *
 * The line above the list is a polite status. It says that the list is
 * loading and then how many bookings there are, so a person who cannot see
 * the list change still hears that it did.
 */

import { useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { ReservationPage, ReservationStatus } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import type { QueryPhase } from '../../shared/api/query-phase'
import { reservationQueries } from '../../shared/api/reservation-queries'
import { DEFAULT_RESERVATION_PAGE_SIZE, RESERVATION_STATUSES } from '../../shared/api/reservations'
import { ErrorState, LoadingState } from '../../shared/async-states'
import Pagination from '../../shared/pagination'
import { DataTable, PageHeader } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { RESERVATION_STATUS_LABEL } from './customer-labels'
import { NothingToList, UnfinishedLeftOut } from './reservation-list-notes'
import type { NothingToListReason } from './reservation-list-notes'
import { ReservationRow } from './reservation-row'

const FIRST_PAGE = 1
const STATUS_PARAMETER = 'status'
const PAGE_PARAMETER = 'page'

/** The value the filter holds when no status has been chosen. */
const ALL_BOOKINGS = ''

/** The status of a basket that was priced and never held. */
const UNFINISHED: ReservationStatus = 'DRAFT'

/** The smallest page there is. Only its total is read, to count the
 *  unfinished bookings without fetching them. */
const COUNT_ONLY_PAGE_SIZE = 1

/** Skeleton rows to draw while the list loads. */
const LIST_SKELETON_COUNT = 4

function readStatus(value: string | null): ReservationStatus | null {
  return RESERVATION_STATUSES.find((status) => status === value) ?? null
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

/**
 * @param leftOut How many unfinished bookings the list leaves out. The rows
 *   the server counts include them, so the range it would give is not said.
 */
function statusLine(
  phase: QueryPhase,
  data: ReservationPage | undefined,
  status: ReservationStatus | null,
  leftOut: number,
): string {
  if (phase === 'loading') return 'Loading your bookings.'
  if (phase !== 'ready' || !data) return 'Your bookings did not load.'
  const total = Math.max(0, data.total - leftOut)
  const count = `${total} ${total === 1 ? 'booking' : 'bookings'}`
  const found = status
    ? `${count} with the status ${RESERVATION_STATUS_LABEL[status]}.`
    : `${count} on your account.`
  const first = (data.page - 1) * data.pageSize + 1
  const last = first + data.items.length - 1
  const showing =
    leftOut === 0 && data.items.length > 0 && data.total > data.items.length
      ? ` Showing ${first} to ${last}.`
      : ''
  return `${found}${showing}`
}

/**
 * Why there is no row to draw, when there is none.
 *
 * @param page The page the server answered with.
 * @param filtered True when the filter asks for one status.
 * @param leftOut How many unfinished bookings the list leaves out.
 */
function whyNothingToList(
  page: ReservationPage,
  filtered: boolean,
  leftOut: number,
): NothingToListReason {
  // The page has rows and every one of them was left out. Either that is all
  // the customer has, or the bookings they made are on other pages.
  if (page.items.length > 0) return page.total > leftOut ? 'unfinishedFillThePage' : 'none'
  if (page.total > 0 && page.page > FIRST_PAGE) return 'pastTheEnd'
  return filtered ? 'noneWithStatus' : 'none'
}

export default function MyReservations() {
  const { user } = useSession()
  const [params, setParams] = useSearchParams()
  const regionRef = useRef<HTMLElement>(null)
  const status = readStatus(params.get(STATUS_PARAMETER))
  const page = readPage(params.get(PAGE_PARAMETER))
  const everyStatus = status === null

  const reservations = useQuery(
    reservationQueries.list({
      status: status ?? undefined,
      page,
      pageSize: DEFAULT_RESERVATION_PAGE_SIZE,
    }),
  )
  const unfinished = useQuery({
    ...reservationQueries.list({
      status: UNFINISHED,
      page: FIRST_PAGE,
      pageSize: COUNT_ONLY_PAGE_SIZE,
    }),
    enabled: everyStatus,
  })
  // The list is ready once both answers are in. The count is only asked for
  // when the unfinished bookings are being left out.
  const listPhase = queryPhase(reservations)
  const phase = listPhase === 'ready' && everyStatus ? queryPhase(unfinished) : listPhase
  const data = reservations.data
  const leftOut = everyStatus ? (unfinished.data?.total ?? 0) : 0
  const shown = (data?.items ?? []).filter(
    (reservation) => !everyStatus || reservation.status !== UNFINISHED,
  )

  /** Write the filter and the page to the address. A default is left out. */
  function show(nextStatus: ReservationStatus | null, nextPage: number) {
    const next = new URLSearchParams()
    if (nextStatus) next.set(STATUS_PARAMETER, nextStatus)
    if (nextPage > FIRST_PAGE) next.set(PAGE_PARAMETER, String(nextPage))
    setParams(next, { replace: true })
  }

  function goToPage(nextPage: number) {
    show(status, nextPage)
    // The new page replaces the list, so focus goes back to the top of it and
    // a keyboard user reads the new page from its first row.
    regionRef.current?.focus()
  }

  function loadAgain() {
    void reservations.refetch()
    if (everyStatus) void unfinished.refetch()
  }

  return (
    <>
      <PageHeader
        screenId="SC-07"
        title="My hires"
        subtitle={`Every booking on the account${user ? ` for ${user.fullName}` : ''}, newest first.`}
        actions={
          <Link to="/" className="btn-primary px-md">
            Book more equipment
          </Link>
        }
      />

      <div className="mb-md max-w-xs">
        <label className="field-label" htmlFor="reservation-status">
          Filter by status
        </label>
        <select
          id="reservation-status"
          className="field-input cursor-pointer"
          value={status ?? ALL_BOOKINGS}
          // A new filter is a new list, so it starts again from the first page.
          onChange={(event) => show(readStatus(event.target.value), FIRST_PAGE)}
        >
          <option value={ALL_BOOKINGS}>All bookings</option>
          {RESERVATION_STATUSES.map((value) => (
            <option key={value} value={value}>
              {RESERVATION_STATUS_LABEL[value]}
            </option>
          ))}
        </select>
      </div>

      <section ref={regionRef} tabIndex={-1} aria-label="My bookings">
        <p className="mb-md text-sm text-slate-soft" role="status">
          {statusLine(phase, data, status, leftOut)}
        </p>

        {phase === 'loading' && <LoadingState shape="rows" count={LIST_SKELETON_COUNT} />}

        {phase === 'failed' && (
          <ErrorState
            what="your bookings"
            error={reservations.error ?? unfinished.error}
            onRetry={loadAgain}
          />
        )}

        {phase === 'ready' && data && (
          <div aria-busy={reservations.isFetching}>
            {leftOut > 0 && (
              <UnfinishedLeftOut count={leftOut} onShow={() => show(UNFINISHED, FIRST_PAGE)} />
            )}
            {shown.length === 0 ? (
              <NothingToList
                reason={whyNothingToList(data, !everyStatus, leftOut)}
                onFirstPage={() => goToPage(FIRST_PAGE)}
                onClearFilter={() => show(null, FIRST_PAGE)}
              />
            ) : (
              <DataTable
                caption="Your bookings, newest first"
                columns={['Booking', 'Hire dates', 'Collect from', 'Status', 'Total with VAT', 'Details']}
              >
                {shown.map((reservation) => (
                  <ReservationRow key={reservation.id} reservation={reservation} />
                ))}
              </DataTable>
            )}
            {data.items.length > 0 && (
              <Pagination
                label="Booking pages"
                page={data.page}
                pageSize={data.pageSize}
                total={data.total}
                onPageChange={goToPage}
              />
            )}
          </div>
        )}
      </section>
    </>
  )
}
