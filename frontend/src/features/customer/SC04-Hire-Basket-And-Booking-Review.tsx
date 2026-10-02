/**
 * SC-04 Hire Basket and Booking Review.
 *
 * The basket, and then a booking in three steps on the one screen. Each step
 * is one request, and the screen shows what the server answered. Reviewing
 * creates the reservation as a draft and brings back its price. Holding takes
 * the equipment for thirty minutes. Confirming books the hire. The steps and
 * the rule that only one request runs at a time are in use-booking.ts.
 *
 * Every figure on this screen is the server's, and so is every decision about
 * what the reservation may do next. The browser prices nothing and keeps no
 * rule of its own.
 *
 * The basket is one period at one collection branch, which is exactly what a
 * reservation is. A visitor may fill it without an account. Reviewing it asks
 * them to sign in and brings them back here.
 *
 * When the view changes, focus moves to the heading of the new view, and a
 * polite status says what the last request did.
 */

import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingCart } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { branchClockTime } from '../../shared/today'
import { EmptyState, PageHeader } from '../../shared/ui'
import { useBasket } from '../../shared/use-basket'
import { useSession } from '../../shared/use-session'
import BasketConfirmed from './basket-confirmed'
import { BookingSteps } from './booking-steps'
import BasketStep from './SC04-Basket-Step'
import type { BasketAudience } from './SC04-Basket-Step'
import HoldStep from './SC04-Hold-Step'
import ReviewStep from './SC04-Review-Step'
import { useBooking } from './use-booking'
import type { BookingView } from './use-booking'

/** What the last request did, for a person who cannot see the view change. */
function outcome(view: BookingView, reservation: Reservation | null): string {
  if (reservation === null || view === 'basket') return ''
  if (view === 'review') return 'Your basket has been priced. Nothing is held yet.'
  if (view === 'confirmed') return `Your hire is confirmed. The reference is ${reservation.reference}.`
  return reservation.status === 'HELD' && reservation.holdExpiresAt !== null
    ? `The equipment is held for you until ${branchClockTime(reservation.holdExpiresAt)}.`
    : ''
}

export default function Basket() {
  const basket = useBasket()
  const { user } = useSession()
  const audience: BasketAudience =
    user === null ? 'visitor' : user.role === 'customer' ? 'customer' : 'staff'
  const booking = useBooking(basket, audience === 'customer')
  const { view, reservation, resume } = booking

  // The first view is where the page opens, and the router has already put
  // focus on the main region. Only a change of view moves it to the heading.
  const heading = useRef<HTMLHeadingElement>(null)
  const shownView = useRef(view)
  useEffect(() => {
    if (shownView.current === view) return
    shownView.current = view
    heading.current?.focus()
  }, [view])

  return (
    <>
      <PageHeader
        screenId="SC-04"
        title="Your hire basket"
        subtitle="Check the dates, the branch and the cost before you confirm. Nothing is charged until you collect."
      />
      <p role="status" className="sr-only">
        {outcome(view, reservation)}
      </p>
      {view !== 'basket' && <BookingSteps view={view} />}

      {resume.loading && view === 'basket' ? (
        <LoadingState label="Picking your booking up where you left it" shape="detail" count={2} />
      ) : resume.error !== null && view === 'basket' ? (
        <ErrorState what="the booking you had started" error={resume.error} onRetry={resume.retry}>
          <button type="button" className="btn-ghost px-md" onClick={() => booking.changeBasket()}>
            Start again from my basket
          </button>
        </ErrorState>
      ) : view === 'confirmed' && reservation !== null ? (
        <BasketConfirmed reservation={reservation} headingRef={heading} />
      ) : view === 'hold' && reservation !== null ? (
        <HoldStep reservation={reservation} booking={booking} headingRef={heading} />
      ) : view === 'review' && reservation !== null ? (
        <ReviewStep reservation={reservation} booking={booking} headingRef={heading} />
      ) : basket.lines.length === 0 ? (
        <div className="card">
          <EmptyState
            title="Your basket is empty"
            body="Pick your dates on the catalogue and add the tools you need. You will see the full cost before anything is held."
            action={
              <Link to="/" className="btn-primary px-lg">
                <ShoppingCart className="h-4 w-4 shrink-0" aria-hidden="true" />
                Browse the catalogue
              </Link>
            }
          />
        </div>
      ) : (
        <BasketStep basket={basket} audience={audience} booking={booking} headingRef={heading} />
      )}
    </>
  )
}
