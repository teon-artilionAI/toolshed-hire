/**
 * SC-13 New Booking and Asset Allocation.
 *
 * A booking made at the counter for a customer who is standing there. The
 * customer comes in the address as `?customer=<id>`, so a reload keeps them,
 * and is read from the API. The booking is collected at the branch the
 * assistant works at, and it may start today.
 *
 * It takes the same three requests an online booking takes, on the same
 * routes, one press of a button each. Making the reservation prices it,
 * holding it sets the units aside, and confirming it books the hire. Each
 * button is disabled while its request is in flight. The steps are in
 * use-counter-booking.ts. Every figure is the server's, and the browser prices
 * nothing.
 *
 * Units are allocated by the server when the booking is held. Nobody picks a
 * unit by hand, so a booking can never point at a unit another booking has.
 *
 * When the step changes, focus moves to the heading of the new step, and a
 * polite status says what the last request did.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import type { CustomerSummary, Reservation } from '../../shared/api/contract'
import { customerQueries } from '../../shared/api/counter-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { branchClockTime, todayInBranchTime } from '../../shared/today'
import { Card, EmptyState, Notice, PageHeader, StatusPill } from '../../shared/ui'
import { emptyDraft } from './booking-draft'
import type { BookingDraft } from './booking-draft'
import {
  ACCOUNT_STANDING_LABEL,
  ACCOUNT_STANDING_PILL,
  NO_BOOKING_BECAUSE,
  canBookFor,
} from './counter-labels'
import { CUSTOMERS_PATH, CUSTOMER_PARAMETER, customerHref } from './counter-links'
import { isNotOnFile } from './counter-refusal'
import { StepList } from './counter-steps'
import { BookingConfirmed } from './SC13-Booking-Confirmed'
import { BookingLinesStep } from './SC13-Booking-Lines'
import { BookingReviewStep } from './SC13-Booking-Review'
import { useCounterBooking } from './use-counter-booking'
import type { CounterBookingView } from './use-counter-booking'
import { WorkBranchGate } from './work-branch-gate'
import type { CounterBranch } from './work-branch-gate'

const STEPS = [
  'Choose the dates and the tools',
  'Check the cost',
  'Confirm the booking',
  'The booking is confirmed',
] as const

const STEP_OF: Record<CounterBookingView, number> = { lines: 0, review: 1, held: 2, confirmed: 3 }

/** What the last request did, for a person who cannot see the step change. */
function outcome(view: CounterBookingView, reservation: Reservation | null): string {
  if (reservation === null) return ''
  if (view === 'review') return 'The booking has been priced. Nothing is held yet.'
  if (view === 'confirmed') return `The booking is confirmed. The reference is ${reservation.reference}.`
  return reservation.status === 'HELD' && reservation.holdExpiresAt !== null
    ? `The units are held until ${branchClockTime(reservation.holdExpiresAt)}.`
    : ''
}

function CustomerCard({ customer }: { customer: CustomerSummary }) {
  const status = customer.accountStatus
  return (
    <div className="mb-lg flex flex-wrap items-center gap-sm rounded border border-line bg-surface px-md py-sm">
      <p className="min-w-0 break-words text-sm text-ink">
        Booking for <span className="font-semibold">{customer.displayName}</span>,{' '}
        <span className="tabular">{customer.phone}</span>
      </p>
      <StatusPill status={ACCOUNT_STANDING_PILL[status]} label={ACCOUNT_STANDING_LABEL[status]} />
      <Link to={customerHref(customer.id)} className="btn-ghost ml-auto px-md">
        Find someone else
      </Link>
    </div>
  )
}

function BookingFlow({ customer, branch }: { customer: CustomerSummary; branch: CounterBranch }) {
  const [today] = useState(() => todayInBranchTime())
  const [draft, setDraft] = useState<BookingDraft>(() => emptyDraft(today))
  const booking = useCounterBooking(customer.id, branch.code)
  const { view, reservation } = booking

  // The first step is where the page opens, and the router has already put
  // focus on the main region. Only a change of step moves it to the heading.
  const heading = useRef<HTMLHeadingElement>(null)
  const shownView = useRef(view)
  useEffect(() => {
    if (shownView.current === view) return
    shownView.current = view
    heading.current?.focus()
  }, [view])

  function startAgain() {
    setDraft(emptyDraft(today))
    booking.startAgain()
  }

  return (
    <>
      <CustomerCard customer={customer} />
      <StepList label="Booking steps" steps={STEPS} current={STEP_OF[view]} allDone={view === 'confirmed'} />
      <p role="status" className="sr-only">
        {outcome(view, reservation)}
      </p>

      {booking.blockedBecause !== null ? (
        <Notice tone="error" title={`No booking can be made for ${customer.displayName}`}>
          <p>{booking.blockedBecause}</p>
        </Notice>
      ) : view === 'confirmed' && reservation !== null ? (
        <BookingConfirmed
          reservation={reservation}
          customer={customer}
          today={today}
          headingRef={heading}
          onStartAgain={startAgain}
        />
      ) : view !== 'lines' && reservation !== null ? (
        <BookingReviewStep reservation={reservation} booking={booking} headingRef={heading} />
      ) : (
        <BookingLinesStep
          draft={draft}
          onDraft={setDraft}
          branch={branch}
          today={today}
          booking={booking}
          headingRef={heading}
        />
      )}
    </>
  )
}

function FindTheCustomerFirst() {
  return (
    <div className="card">
      <EmptyState
        title="Find the customer first"
        body="A booking at the counter is always for a customer on file. Find them, or register them as a walk in, and start the booking from there."
        action={
          <Link to={CUSTOMERS_PATH} className="btn-primary px-lg">
            <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
            Find a customer
          </Link>
        }
      />
    </div>
  )
}

function BookingDesk({ customerId, branch }: { customerId: string; branch: CounterBranch }) {
  const customer = useQuery(customerQueries.detail(customerId))
  const phase = queryPhase(customer)

  if (phase === 'failed' && isNotOnFile(customer.error)) {
    return (
      <Notice tone="error" title="We cannot find that customer">
        <p>
          The customer in the address is not on file.{' '}
          <Link to={CUSTOMERS_PATH} className="font-medium underline">
            Find the customer again
          </Link>
          .
        </p>
      </Notice>
    )
  }
  if (phase === 'failed') {
    return <ErrorState what="the customer" error={customer.error} onRetry={() => void customer.refetch()} />
  }
  if (!customer.data) return <LoadingState label="Loading the customer" shape="detail" count={1} />

  const chosen = customer.data
  if (!canBookFor(chosen.accountStatus)) {
    return (
      <>
        <CustomerCard customer={chosen} />
        <Card title="No booking can be made">
          <p className="text-sm text-ink">{NO_BOOKING_BECAUSE[chosen.accountStatus]}</p>
        </Card>
      </>
    )
  }
  return <BookingFlow customer={chosen} branch={branch} />
}

export default function NewBooking() {
  const [params] = useSearchParams()
  const customerId = params.get(CUSTOMER_PARAMETER)
  return (
    <>
      <PageHeader
        screenId="SC-13"
        title="New booking"
        subtitle="Choose the dates and the tools, check the cost, then hold and confirm. The units are picked for you."
      />
      {customerId === null || customerId === '' ? (
        <FindTheCustomerFirst />
      ) : (
        <WorkBranchGate>
          {(branch) => <BookingDesk key={customerId} customerId={customerId} branch={branch} />}
        </WorkBranchGate>
      )}
    </>
  )
}
