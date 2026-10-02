/**
 * Step three of a booking on SC-04. The hire is confirmed.
 *
 * This is shown only for a reservation the server says is confirmed, and the
 * sentence about the confirmation email is written only then. It gives the
 * reference, names the branch and the day, says what to bring, and repeats
 * the server's figures. A confirmation that only says "thank you" leaves the
 * customer ringing the branch to ask what happens next.
 */

import type { RefObject } from 'react'
import { Link } from 'react-router-dom'
import type { Reservation } from '../../shared/api/contract'
import { formatDate } from '../../shared/format'
import { Card, Notice } from '../../shared/ui'
import { StepHeading } from './booking-steps'
import { MY_RESERVATIONS_PATH, reservationHref } from './reservation-links'
import { ReservationLines, ReservationTermsCard, ReservationTotals } from './reservation-figures'

export default function BasketConfirmed({
  reservation,
  headingRef,
}: {
  reservation: Reservation
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const confirmed = reservation.status === 'CONFIRMED'
  return (
    <>
      <StepHeading headingRef={headingRef}>Step 3 of 3. Your hire is confirmed</StepHeading>
      {confirmed && (
        <Notice tone="success" title={`Booking ${reservation.reference} is confirmed`}>
          <p>
            A confirmation email is on its way to you. Collect from {reservation.branchName} on{' '}
            {formatDate(reservation.from)}, and bring your ID and the card you are paying with.
          </p>
        </Notice>
      )}
      <div className="mt-lg grid gap-lg lg:grid-cols-5">
        <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
          <ReservationTermsCard reservation={reservation} />
          <Card title="What you booked">
            <ReservationLines reservation={reservation} />
          </Card>
        </div>
        <div className="min-w-0 lg:col-span-2">
          <Card title="What it costs">
            <ReservationTotals reservation={reservation} />
            <p className="mt-md text-sm text-slate-soft">You pay at the counter when you collect.</p>
            <div className="mt-lg flex flex-wrap gap-sm">
              <Link to={MY_RESERVATIONS_PATH} className="btn-primary px-lg">
                See my hires
              </Link>
              <Link to={reservationHref(reservation.reference)} className="btn-secondary px-lg">
                View this booking
              </Link>
              <Link to="/" className="btn-secondary px-lg">
                Hire something else
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
