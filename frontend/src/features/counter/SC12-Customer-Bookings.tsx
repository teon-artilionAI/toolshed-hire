/**
 * One customer and their bookings, on SC-12.
 *
 * The customer is read by their key, from the address, so a reload keeps them
 * on the screen. Their bookings come from the reservation list for that
 * customer, at every branch, newest first.
 *
 * A booking that is confirmed, starts today or earlier and is collected at the
 * branch the assistant works at is ready to go out, and has "Check out" beside
 * it. The server still has the last word on the checkout screen. A booking for
 * another branch says where it is collected.
 *
 * When an assistant chooses a customer, focus moves to the customer's name, so
 * a keyboard or screen reader user lands on what they chose.
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarPlus, PackageCheck } from 'lucide-react'
import type { CustomerSummary, Reservation } from '../../shared/api/contract'
import { customerQueries } from '../../shared/api/counter-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { reservationQueries } from '../../shared/api/reservation-queries'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import Pagination from '../../shared/pagination'
import { todayInBranchTime } from '../../shared/today'
import { Notice, StatusPill } from '../../shared/ui'
import {
  ACCOUNT_STANDING_LABEL,
  ACCOUNT_STANDING_PILL,
  ID_DOCUMENT_LABEL,
  NO_BOOKING_BECAUSE,
  canBookFor,
} from './counter-labels'
import { bookingHref, checkoutHref } from './counter-links'
import { isNotOnFile } from './counter-refusal'
import { FIRST_PAGE } from './SC12-Search-Results'
import type { CounterBranch } from './work-branch-gate'

/** How many bookings a page of one customer's list holds. */
const BOOKING_PAGE_SIZE = 10

/** Whether a booking is ready to go out over this counter today. */
function readyToCheckOut(reservation: Reservation, branchCode: string, today: string): boolean {
  return reservation.status === 'CONFIRMED' && reservation.from <= today && reservation.branchCode === branchCode
}

function linesInWords(reservation: Reservation): string {
  return reservation.lines.map((line) => `${line.quantity} x ${line.modelName}`).join(', ')
}

function BookingRow({ reservation, branch, today }: { reservation: Reservation; branch: CounterBranch; today: string }) {
  const ready = readyToCheckOut(reservation, branch.code, today)
  const elsewhere = reservation.status === 'CONFIRMED' && reservation.branchCode !== branch.code
  return (
    <li className="flex flex-wrap items-start justify-between gap-md border-t border-line py-md first:border-t-0">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-sm">
          <span className="font-mono text-sm font-medium text-ink">{reservation.reference}</span>
          <StatusPill status={reservation.status} />
        </p>
        <p className="mt-xs break-words text-sm text-ink">{linesInWords(reservation)}</p>
        <p className="tabular text-sm text-slate-soft">
          {formatDate(reservation.from)} to {formatDate(reservation.to)}, {reservation.branchName}
        </p>
        {elsewhere && (
          <p className="text-sm text-slate-soft">Collected at {reservation.branchName}, not at this counter.</p>
        )}
      </div>
      {ready && (
        <Link to={checkoutHref(reservation.reference)} className="btn-primary px-md">
          <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
          Check out{' '}
          <span className="sr-only">{reservation.reference}</span>
        </Link>
      )}
    </li>
  )
}

function CustomerBookings({ customer, branch }: { customer: CustomerSummary; branch: CounterBranch }) {
  const [page, setPage] = useState(FIRST_PAGE)
  const [today] = useState(() => todayInBranchTime())
  const bookings = useQuery(
    reservationQueries.list({ customerProfileId: customer.id, page, pageSize: BOOKING_PAGE_SIZE }),
  )
  const phase = queryPhase(bookings)
  const data = bookings.data

  return (
    <section aria-label={`Bookings for ${customer.displayName}`} className="mt-lg">
      <h3 className="mb-sm text-sm font-semibold uppercase tracking-wide text-slate-soft">Their bookings</h3>
      {phase === 'loading' && <LoadingState label="Loading their bookings" shape="rows" count={2} />}
      {phase === 'failed' && (
        <ErrorState what="their bookings" error={bookings.error} onRetry={() => void bookings.refetch()} />
      )}
      {phase === 'ready' && data && data.items.length === 0 && (
        <p className="text-sm text-slate-soft">No bookings yet.</p>
      )}
      {phase === 'ready' && data && data.items.length > 0 && (
        <>
          <ul aria-busy={bookings.isFetching}>
            {data.items.map((reservation) => (
              <BookingRow key={reservation.id} reservation={reservation} branch={branch} today={today} />
            ))}
          </ul>
          <Pagination
            label="Pages of their bookings"
            page={data.page}
            pageSize={data.pageSize}
            total={data.total}
            onPageChange={setPage}
          />
        </>
      )}
    </section>
  )
}

export function ChosenCustomer({
  customerId,
  branch,
  focusRequest,
  justRegistered,
}: {
  customerId: string
  branch: CounterBranch
  /** Goes up by one each time the assistant chooses a customer. Zero means
   *  the customer came from the address, and focus is left where it is. */
  focusRequest: number
  /** True right after this customer was registered as a walk in. */
  justRegistered: boolean
}) {
  const customer = useQuery(customerQueries.detail(customerId))
  const phase = queryPhase(customer)
  const heading = useRef<HTMLHeadingElement>(null)
  const loaded = customer.data !== undefined

  useEffect(() => {
    if (focusRequest > 0 && loaded) heading.current?.focus()
  }, [focusRequest, loaded])

  if (phase === 'failed' && isNotOnFile(customer.error)) {
    return (
      <Notice tone="error" title="We cannot find that customer">
        <p>The customer in the address is not on file. Search for them again.</p>
      </Notice>
    )
  }
  if (phase === 'failed') {
    return <ErrorState what="the customer" error={customer.error} onRetry={() => void customer.refetch()} />
  }
  if (!customer.data) return <LoadingState label="Loading the customer" shape="detail" count={1} />

  const chosen = customer.data
  const status = chosen.accountStatus
  return (
    <section className="card p-lg" aria-labelledby="chosen-customer-heading">
      {justRegistered && (
        <div className="mb-md">
          <Notice tone="success" title={`${chosen.displayName} is on file`}>
            <p>Registered at {branch.name} as a walk in with no login. You can book for them straight away.</p>
          </Notice>
        </div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div className="min-w-0">
          <h2
            id="chosen-customer-heading"
            ref={heading}
            tabIndex={-1}
            className="break-words text-lg font-semibold text-ink"
          >
            {chosen.displayName}
          </h2>
          {chosen.companyName && <p className="break-words text-sm text-slate-soft">{chosen.companyName}</p>}
          <p className="tabular mt-xs text-sm text-ink">{chosen.phone}</p>
          <p className="break-all text-sm text-slate-soft">{chosen.email ?? 'No email on file'}</p>
          <p className="text-sm text-slate-soft">
            {ID_DOCUMENT_LABEL[chosen.idDocumentType]} ending {chosen.idDocumentLast4}
            {chosen.noShowCount > 0
              ? `. ${chosen.noShowCount} ${chosen.noShowCount === 1 ? 'no show' : 'no shows'} on record.`
              : '.'}
          </p>
          <div className="mt-sm flex flex-wrap gap-xs">
            <StatusPill status={ACCOUNT_STANDING_PILL[status]} label={ACCOUNT_STANDING_LABEL[status]} />
            <StatusPill status={chosen.hasLogin ? 'CONFIRMED' : 'DRAFT'} label={chosen.hasLogin ? 'Has a login' : 'No login'} />
          </div>
        </div>
        {canBookFor(status) && (
          <Link to={bookingHref(chosen.id)} className="btn-primary px-lg">
            <CalendarPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
            New booking for {chosen.displayName}
          </Link>
        )}
      </div>
      {!canBookFor(status) && (
        <div className="mt-md">
          <Notice tone="error" title={`No booking can be made for ${chosen.displayName}`}>
            <p>{NO_BOOKING_BECAUSE[status]}</p>
          </Notice>
        </div>
      )}
      <CustomerBookings key={chosen.id} customer={chosen} branch={branch} />
    </section>
  )
}
