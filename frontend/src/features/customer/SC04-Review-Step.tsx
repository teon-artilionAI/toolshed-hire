/**
 * Step one of a booking on SC-04. The cost, before anything is held.
 *
 * The reservation exists as a draft and the server has priced it. This view
 * writes out what the server sent. Every line, the subtotal, the VAT and the
 * total, and the deposit apart from them. The browser works out none of it.
 *
 * The button holds the equipment. It is offered when the server says the
 * reservation can be held, and not otherwise. When the hold is refused because
 * a line cannot be supplied, the server's sentence names the model and the
 * dates, and the person is offered the basket to change.
 */

import type { RefObject } from 'react'
import { Loader2, PackageCheck, Pencil } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { Card, Notice } from '../../shared/ui'
import { AccountOnHoldNotice, BookingRefusalNotice } from './booking-refusal-notice'
import { StepHeading } from './booking-steps'
import { ReservationLines, ReservationTermsCard, ReservationTotals } from './reservation-figures'
import type { Booking } from './use-booking'

export default function ReviewStep({
  reservation,
  booking,
  headingRef,
}: {
  reservation: Reservation
  booking: Booking
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const busy = booking.pending !== null
  const refusal = booking.failure?.action === 'hold' ? booking.failure.refusal : null
  const changeBasket = (
    <button type="button" className="btn-secondary px-md" disabled={busy} onClick={() => booking.changeBasket()}>
      <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
      Change my basket
    </button>
  )

  return (
    <>
      <StepHeading headingRef={headingRef}>Step 1 of 3. Review the cost</StepHeading>
      <div className="grid gap-lg lg:grid-cols-5">
        <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
          <ReservationTermsCard reservation={reservation} />
          <Card title="What you are hiring">
            <ReservationLines reservation={reservation} />
          </Card>
        </div>

        <div className="min-w-0 lg:col-span-2 lg:sticky lg:top-24 lg:self-start">
          <Card title="What it costs">
            <ReservationTotals reservation={reservation} />

            {refusal && (
              <div className="mt-md">
                <BookingRefusalNotice
                  refusal={refusal}
                  conflictTitle="We could not hold everything in your basket"
                  faultHeading="We could not hold the equipment"
                  onRetry={booking.hold}
                >
                  {refusal.kind === 'conflict' ? changeBasket : null}
                </BookingRefusalNotice>
              </div>
            )}

            <div className="mt-md flex flex-col gap-sm">
              {booking.blockedBecause !== null ? (
                <AccountOnHoldNotice because={booking.blockedBecause} />
              ) : reservation.canHold ? (
                <>
                  <button
                    type="button"
                    className="btn-primary w-full"
                    disabled={busy}
                    onClick={booking.hold}
                  >
                    {booking.pending === 'hold' ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                    ) : (
                      <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    {booking.pending === 'hold' ? 'Holding the equipment' : 'Hold this equipment'}
                  </button>
                  <p className="text-sm text-slate-soft">
                    Holding sets the equipment aside for you while you confirm, so nobody else can
                    book it in the meantime. Nothing is charged until you collect.
                  </p>
                </>
              ) : (
                <Notice tone="warn" title="This basket cannot be held right now">
                  <p>Change the basket and review it again, or ring your branch.</p>
                </Notice>
              )}
              {refusal?.kind !== 'conflict' && changeBasket}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
