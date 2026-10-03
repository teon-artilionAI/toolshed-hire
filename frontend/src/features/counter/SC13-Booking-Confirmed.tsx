/**
 * What SC-13 shows once the booking is confirmed.
 *
 * The reference, the units the server set aside, and the money the customer
 * hands over at collection. An assistant reads this back to the customer, so
 * it is written to be read out loud. Every figure is the server's.
 *
 * A booking that starts today can go out at once, so it offers the checkout.
 * One that starts later is collected on its day, from the diary.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import { CalendarPlus, PackageCheck } from 'lucide-react'
import type { CustomerSummary, Reservation } from '../../shared/api/contract'
import { formatDate, money } from '../../shared/format'
import { Card, Notice } from '../../shared/ui'
import { BookingLines, BookingTotals } from './booking-figures'
import { checkoutHref, customerHref } from './counter-links'
import { StepHeading } from './counter-steps'

export function BookingConfirmed({
  reservation,
  customer,
  today,
  headingRef,
  onStartAgain,
}: {
  reservation: Reservation
  customer: CustomerSummary
  today: string
  headingRef: RefObject<HTMLHeadingElement | null>
  onStartAgain: () => void
}) {
  const goesOutToday = reservation.from === today
  return (
    <>
      <StepHeading headingRef={headingRef}>Step 4 of 4. The booking is confirmed</StepHeading>
      <Notice tone="success" title={`Booking ${reservation.reference} is confirmed`}>
        <p>
          {customer.displayName} collects from {reservation.branchName} on {formatDate(reservation.from)}{' '}
          and brings it back on {formatDate(reservation.to)}. Take a deposit of{' '}
          {money(reservation.depositTotal)} at collection.
        </p>
      </Notice>

      <div className="mt-lg grid gap-lg lg:grid-cols-5">
        <div className="min-w-0 lg:col-span-3">
          <Card title="Units set aside">
            <BookingLines reservation={reservation} />
          </Card>
        </div>
        <div className="min-w-0 lg:col-span-2">
          <Card title="What it costs">
            <BookingTotals reservation={reservation} />
            <div className="mt-lg flex flex-col gap-sm">
              {goesOutToday ? (
                <Link to={checkoutHref(reservation.reference)} className="btn-primary w-full">
                  <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Check out now
                </Link>
              ) : (
                <p className="text-sm text-slate-soft">
                  It goes out on {formatDate(reservation.from)}. Check it out from the customer's
                  bookings on that day.
                </p>
              )}
              <button type="button" className="btn-secondary w-full" onClick={onStartAgain}>
                <CalendarPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
                Another booking for {customer.displayName}
              </button>
              <Link to={customerHref(customer.id)} className="btn-ghost w-full">
                Back to {customer.displayName}
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
