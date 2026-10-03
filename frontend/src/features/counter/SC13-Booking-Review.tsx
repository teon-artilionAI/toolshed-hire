/**
 * Steps two and three of a counter booking on SC-13. The cost, then the hold.
 *
 * The reservation exists and the server has priced it. These views write out
 * what the server sent and offer the one request that comes next. Holding sets
 * the units aside, and the server names them, so the assistant can read the
 * tags back. Confirming books the hire.
 *
 * A conflict on the hold shows the server's sentence, which names the model and
 * the dates that could not be supplied, and offers the tools to change. A
 * conflict on the confirmation means the hold ran out, and the same way back
 * is offered. Going back cancels the reservation first when it can be, so the
 * units are free for the next try.
 */

import type { RefObject } from 'react'
import { CircleCheck, Loader2, PackageCheck, Pencil } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { formatDate } from '../../shared/format'
import { branchClockTime } from '../../shared/today'
import { Card, Notice } from '../../shared/ui'
import { BookingLines, BookingTotals } from './booking-figures'
import { StepHeading } from './counter-steps'
import type { CounterBooking } from './use-counter-booking'

/** The way back to the tools. Secondary, unless it is the only way on. */
function ChangeTools({ booking, primary = false }: { booking: CounterBooking; primary?: boolean }) {
  return (
    <button
      type="button"
      className={`${primary ? 'btn-primary' : 'btn-secondary'} w-full`}
      disabled={booking.pending !== null}
      onClick={booking.changeTools}
    >
      {booking.pending === 'release' ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
      )}
      {booking.pending === 'release' ? 'Giving the booking up' : 'Change the dates or the tools'}
    </button>
  )
}

/** Why the last request on this step did not work, in the server's words when it sent any. */
function StepFailure({ booking, onRetry }: { booking: CounterBooking; onRetry: () => void }) {
  const failure = booking.failure
  if (failure === null || failure.refusal.kind === 'accountOnHold') return null
  // A conflict on the confirmation is the hold running out, and the step says
  // that itself, with the server's sentence.
  if (failure.action === 'confirm' && failure.refusal.kind === 'conflict') return null
  const heading =
    failure.action === 'hold'
      ? 'We could not hold the equipment'
      : failure.action === 'confirm'
        ? 'We could not confirm the booking'
        : 'We could not give the booking up'
  if (failure.refusal.kind === 'fault') {
    return <ErrorState heading={heading} error={failure.refusal.error} onRetry={onRetry} />
  }
  return (
    <Notice tone="error" title={heading}>
      <p>{failure.refusal.detail}</p>
    </Notice>
  )
}

export function BookingReviewStep({
  reservation,
  booking,
  headingRef,
}: {
  reservation: Reservation
  booking: CounterBooking
  headingRef: RefObject<HTMLHeadingElement | null>
}) {
  const busy = booking.pending !== null
  const held = booking.view === 'held'
  const serverSaidLapsed =
    booking.failure?.action === 'confirm' && booking.failure.refusal.kind === 'conflict'
      ? booking.failure.refusal.detail
      : null
  const lapsed = held && (reservation.status !== 'HELD' || serverSaidLapsed !== null)
  const conflictOnHold = booking.failure?.action === 'hold' && booking.failure.refusal.kind === 'conflict'
  const retry =
    booking.failure?.action === 'confirm'
      ? booking.confirm
      : booking.failure?.action === 'release'
        ? booking.changeTools
        : booking.hold

  return (
    <>
      <StepHeading headingRef={headingRef}>
        {held ? 'Step 3 of 4. Confirm the booking' : 'Step 2 of 4. Check the cost'}
      </StepHeading>
      <div className="grid gap-lg lg:grid-cols-5">
        <div className="flex min-w-0 flex-col gap-lg lg:col-span-3">
          <Card title="When and where">
            <p className="tabular text-sm text-ink">
              {formatDate(reservation.from)} to {formatDate(reservation.to)}, {reservation.hireDays}{' '}
              {reservation.hireDays === 1 ? 'day' : 'days'}, collected from {reservation.branchName}.
            </p>
          </Card>
          <Card title="What is on the booking">
            <BookingLines reservation={reservation} />
          </Card>
        </div>

        <div className="min-w-0 lg:col-span-2">
          <Card title="What it costs">
            <BookingTotals reservation={reservation} />

            <div className="mt-md flex flex-col gap-sm">
              <StepFailure booking={booking} onRetry={retry} />

              {held && lapsed && (
                <Notice tone="warn" title="The hold has run out">
                  <p>
                    {serverSaidLapsed ?? 'The units went back on the shelf.'} Change the dates or the
                    tools and try again.
                  </p>
                </Notice>
              )}
              {held && !lapsed && reservation.holdExpiresAt !== null && (
                <p className="tabular text-sm text-ink">
                  The units are held until {branchClockTime(reservation.holdExpiresAt)}. Confirm before
                  then to keep them.
                </p>
              )}

              {!held && reservation.canHold && !conflictOnHold && (
                <button type="button" className="btn-primary w-full" disabled={busy} onClick={booking.hold}>
                  {booking.pending === 'hold' ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                  ) : (
                    <PackageCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                  )}
                  {booking.pending === 'hold' ? 'Holding the equipment' : 'Hold the equipment'}
                </button>
              )}
              {!held && !reservation.canHold && (
                <Notice tone="warn" title="This booking cannot be held right now">
                  <p>Change the dates or the tools and work out the cost again.</p>
                </Notice>
              )}
              {held && !lapsed && reservation.canConfirm && (
                <button type="button" className="btn-primary w-full" disabled={busy} onClick={booking.confirm}>
                  {booking.pending === 'confirm' ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
                  ) : (
                    <CircleCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                  )}
                  {booking.pending === 'confirm' ? 'Confirming the booking' : 'Confirm the booking'}
                </button>
              )}

              <ChangeTools booking={booking} primary={conflictOnHold || lapsed} />
              {!held && (
                <p className="text-sm text-slate-soft">
                  Holding sets the units aside so nobody else can book them while you confirm.
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
