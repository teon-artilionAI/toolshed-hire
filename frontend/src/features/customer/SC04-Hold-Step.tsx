/**
 * Step two of a booking on SC-04. The equipment is held, and the clock is
 * running.
 *
 * The server says until when the hold stands. The view counts down to that
 * moment, in hold-countdown.tsx, and offers the confirmation while the server
 * says the reservation can be confirmed.
 *
 * A hold ends in one of three ways and the view says which. The time on the
 * screen reaches zero. The server answers a confirmation with a conflict,
 * which means the hold was already gone. Or a reload finds the reservation
 * expired. A lapsed hold cannot be held again, so "Hold it again" makes a new
 * reservation from the same basket and holds that.
 *
 * The line a screen reader hears is one polite status that is always on the
 * page. It speaks a few times as the time runs down and once when it runs
 * out. Nothing here takes focus away from where the person is.
 */

import type { RefObject } from 'react'
import { CircleCheck, Loader2, PackageCheck, Pencil } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { Card, Notice } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import {
  AccountOnHoldNotice,
  BookingRefusalNotice,
  EmailNotVerifiedNotice,
} from './booking-refusal-notice'
import { StepHeading } from './booking-steps'
import HoldCountdown from './hold-countdown'
import { HOLD_RAN_OUT, spokenTimeLeft } from './hold-time'
import { ReservationLines, ReservationTermsCard, ReservationTotals } from './reservation-figures'
import type { Booking } from './use-booking'
import { useSecondsLeft } from './use-seconds-left'

/** What the box says when the countdown on the screen is what ended the hold. */
const TIME_RAN_OUT = 'The time to confirm ran out, so the equipment went back on the shelf.'

export default function HoldStep({
  reservation,
  booking,
  headingRef,
}: {
  reservation: Reservation
  booking: Booking
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const { user } = useSession()
  const held = reservation.status === 'HELD'
  const secondsLeft = useSecondsLeft(held ? reservation.holdExpiresAt : null)
  const lapsed = !held || booking.holdLapsed || secondsLeft === 0
  const busy = booking.pending !== null
  const failure = booking.failure
  // A conflict on a confirmation is the hold having run out, and the box below
  // says so. Every other refusal is shown as it is.
  const refusal =
    failure !== null && !(failure.action === 'confirm' && failure.refusal.kind === 'conflict')
      ? failure.refusal
      : null
  const serverSaid =
    failure?.action === 'confirm' && failure.refusal.kind === 'conflict'
      ? failure.refusal.detail
      : null
  const blocked = booking.blockedBecause
  // The hold stands and the server still says it cannot be confirmed. The
  // session knows whether the email address is verified, so the view can say
  // why. When a refusal has already said so, it is not said twice.
  const explainNoConfirm =
    blocked === null && !lapsed && !reservation.canConfirm && refusal?.kind !== 'emailNotVerified'

  return (
    <>
      <StepHeading headingRef={headingRef}>Step 2 of 3. Hold the equipment</StepHeading>
      <p role="status" className="sr-only">
        {lapsed
          ? `${HOLD_RAN_OUT} Hold it again to carry on.`
          : spokenTimeLeft(secondsLeft ?? Infinity)}
      </p>
      <div className="grid gap-lg lg:grid-cols-5">
        <div className="min-w-0 lg:col-span-2">
          <Card title={lapsed ? 'The hold has run out' : 'Held for you'}>
            {lapsed ? (
              <div className="rounded border-l-4 border-status-due bg-status-due-wash px-md py-sm">
                <p className="text-sm font-semibold text-status-due">
                  The equipment is no longer held
                </p>
                <p className="mt-xs text-sm text-ink">
                  {serverSaid ?? TIME_RAN_OUT} Your basket is as you left it. Hold it again to
                  carry on.
                </p>
              </div>
            ) : (
              <>
                <p className="mb-md text-sm text-slate-soft">
                  Everything in your basket is set aside for you at {reservation.branchName}.
                  Confirm before the time runs out to keep it.
                </p>
                {reservation.holdExpiresAt !== null && secondsLeft !== null && (
                  <HoldCountdown expiresAt={reservation.holdExpiresAt} secondsLeft={secondsLeft} />
                )}
              </>
            )}

            {refusal && (
              <div className="mt-md">
                <BookingRefusalNotice
                  refusal={refusal}
                  conflictTitle={
                    failure?.action === 'release'
                      ? 'We could not release the hold'
                      : 'We could not hold everything in your basket'
                  }
                  faultHeading={
                    failure?.action === 'confirm'
                      ? 'We could not confirm your hire'
                      : failure?.action === 'release'
                        ? 'We could not release the hold'
                        : 'We could not hold the equipment'
                  }
                  onRetry={
                    failure?.action === 'confirm'
                      ? booking.confirm
                      : failure?.action === 'release'
                        ? () => booking.changeBasket(true)
                        : booking.holdAgain
                  }
                />
              </div>
            )}

            <div className="mt-md flex flex-col gap-sm">
              {blocked !== null && <AccountOnHoldNotice because={blocked} />}
              {blocked === null && lapsed && (
                <button type="button" className="btn-primary w-full" disabled={busy} onClick={booking.holdAgain}>
                  {booking.pending === 'hold' ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                  ) : (
                    <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                  )}
                  {booking.pending === 'hold' ? 'Holding the equipment' : 'Hold it again'}
                </button>
              )}
              {blocked === null && !lapsed && reservation.canConfirm && (
                <button type="button" className="btn-primary w-full" disabled={busy} onClick={booking.confirm}>
                  {booking.pending === 'confirm' ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                  ) : (
                    <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                  )}
                  {booking.pending === 'confirm' ? 'Confirming your hire' : 'Confirm this hire'}
                </button>
              )}
              {explainNoConfirm && user?.emailVerified === false && <EmailNotVerifiedNotice />}
              {explainNoConfirm && user?.emailVerified !== false && (
                <Notice tone="warn" title="This hire cannot be confirmed online right now">
                  <p>
                    Ring {reservation.branchName} and they can confirm it for you while it is held.
                  </p>
                </Notice>
              )}
              <button
                type="button"
                className="btn-secondary w-full"
                disabled={busy}
                onClick={() => booking.changeBasket(!lapsed)}
              >
                {booking.pending === 'release' ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                ) : (
                  <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
                )}
                {lapsed ? 'Change my basket' : 'Release the hold and change my basket'}
              </button>
              <p className="text-center text-sm text-slate-soft">
                You pay at the counter when you collect.
              </p>
            </div>
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
          <ReservationTermsCard reservation={reservation} />
          <Card title="What it costs">
            <ReservationLines reservation={reservation} />
            <div className="mt-md">
              <ReservationTotals reservation={reservation} />
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
