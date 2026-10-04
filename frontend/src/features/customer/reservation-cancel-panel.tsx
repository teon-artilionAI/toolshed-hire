/**
 * Cancelling a booking, on SC-08.
 *
 * Whether a booking can be cancelled is the server's call. It sends
 * `canCancel` with every reservation, worked out for the person asking and the
 * moment they asked, and this panel offers the cancellation from that flag and
 * from nothing else. It keeps no list of statuses of its own.
 *
 * Cancelling asks first, because it cannot be undone. The reason is optional.
 * The request is sent once, the button is disabled while it is in flight, and
 * what the panel shows afterwards is the reservation the server answered with.
 * When the server refuses, its own sentence is shown, and the reservation is
 * read again so the panel stops offering what is no longer possible.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { CalendarX2, Loader2, Undo2 } from 'lucide-react'
import type { Reservation } from '../../shared/api/contract'
import { MAX_CANCELLATION_REASON_LENGTH, cancelReservation } from '../../shared/api/reservations'
import { branchDateTime } from '../../shared/today'
import { Card, Field, Notice } from '../../shared/ui'
import { describeBookingFailure } from './booking-refusal'
import type { BookingRefusal } from './booking-refusal'
import { BookingRefusalNotice } from './booking-refusal-notice'

const REASON_ID = 'cancel-reason'

/** How tall the box for the reason opens, in lines of text. */
const REASON_ROWS = 3
const CARD_TITLE = 'Cancelling this booking'

/**
 * Why a booking the server will not let this person cancel cannot be
 * cancelled, by where it stands. A booking still to go out can be changed by
 * ringing the branch. One that has gone out, came back, ran out or was never
 * collected has nothing left to cancel.
 */
function NotCancellable({ reservation }: { reservation: Reservation }) {
  const why: Partial<Record<Reservation['status'], string>> = {
    COLLECTED: `The equipment has been collected, so the booking can no longer be cancelled. Bring it back to ${reservation.branchName} by the return date.`,
    RETURNED: 'The equipment has come back and the hire is finished, so there is nothing to cancel.',
    EXPIRED: 'The hold ran out before the booking was confirmed, so there is nothing to cancel.',
    NO_SHOW: 'The equipment was not collected on the day, so the booking was closed. There is nothing to cancel.',
  }
  return (
    <p className="text-sm text-slate-soft">
      {why[reservation.status] ??
        `This booking cannot be cancelled online. If you need to change it, ring ${reservation.branchName}.`}
    </p>
  )
}

/** What the server recorded about a cancellation. */
function CancelledNotice({ reservation }: { reservation: Reservation }) {
  return (
    <Notice tone="info" title="This booking has been cancelled">
      <p>
        {reservation.cancelledAt !== null
          ? `It was cancelled on ${branchDateTime(reservation.cancelledAt)}. `
          : ''}
        The equipment is back in stock at {reservation.branchName}.
      </p>
      {reservation.cancellationReason !== null && (
        <p className="mt-xs">The reason given was "{reservation.cancellationReason}".</p>
      )}
    </Notice>
  )
}

export function CancellationPanel({
  reservation,
  onCancelled,
  onOutOfDate,
}: {
  reservation: Reservation
  /** Called with the reservation the server answered a cancellation with. */
  onCancelled: (cancelled: Reservation) => void
  /** Called when the server refused, so the reservation is read again. */
  onOutOfDate: () => void
}) {
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState(false)
  const [refusal, setRefusal] = useState<BookingRefusal | null>(null)
  const [justCancelled, setJustCancelled] = useState(false)
  const inFlight = useRef(false)
  const question = useRef<HTMLHeadingElement>(null)
  const result = useRef<HTMLDivElement>(null)

  // Focus follows what the person just did. To the question when it opens, and
  // to the result when the buttons they were on have gone.
  useEffect(() => {
    if (asking) question.current?.focus()
  }, [asking])
  useEffect(() => {
    if (justCancelled && !reservation.canCancel) result.current?.focus()
  }, [justCancelled, reservation.canCancel])

  async function cancel(): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setRefusal(null)
    try {
      const cancelled = await cancelReservation(reservation.id, reason.trim() || null)
      setAsking(false)
      setJustCancelled(true)
      onCancelled(cancelled)
    } catch (cause) {
      const described = describeBookingFailure(cause)
      setRefusal(described)
      if (described.kind === 'conflict') onOutOfDate()
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void cancel()
  }

  const reasonError = refusal?.kind === 'refused' ? refusal.fields.reason : undefined
  const refusalNotice = refusal && (
    <div className="mt-md">
      <BookingRefusalNotice
        refusal={refusal}
        conflictTitle="This booking can no longer be cancelled"
        refusedTitle="We cannot cancel with those details"
        faultHeading="We could not cancel this booking"
        onRetry={() => void cancel()}
      />
    </div>
  )

  if (!reservation.canCancel) {
    return (
      <Card title={CARD_TITLE}>
        <div ref={result} tabIndex={-1}>
          {reservation.status === 'CANCELLED' ? (
            <CancelledNotice reservation={reservation} />
          ) : (
            <NotCancellable reservation={reservation} />
          )}
        </div>
        {refusal?.kind === 'conflict' && refusalNotice}
      </Card>
    )
  }

  return (
    <Card title={CARD_TITLE}>
      <p className="text-sm text-slate-soft">
        You can still cancel this booking online. The deposit is only taken at the counter, when
        the equipment is handed over.
      </p>

      {!asking && refusalNotice}

      {asking ? (
        <form noValidate onSubmit={handleSubmit} className="mt-md rounded-lg border border-line bg-muted p-md">
          <h3 ref={question} tabIndex={-1} className="text-base font-semibold text-ink">
            Cancel {reservation.reference}?
          </h3>
          <p className="mt-xs text-sm text-slate-soft">
            The equipment goes back into stock straight away and someone else can book it. This
            cannot be undone.
          </p>

          <div className="mt-md">
            <Field
              label="Why are you cancelling? You can leave this empty."
              htmlFor={REASON_ID}
              help={`Up to ${MAX_CANCELLATION_REASON_LENGTH} characters.`}
              error={reasonError}
            >
              <textarea
                id={REASON_ID}
                className="field-input"
                rows={REASON_ROWS}
                maxLength={MAX_CANCELLATION_REASON_LENGTH}
                value={reason}
                disabled={pending}
                aria-invalid={reasonError ? true : undefined}
                aria-describedby={
                  reasonError ? `${REASON_ID}-help ${REASON_ID}-error` : `${REASON_ID}-help`
                }
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
          </div>

          {refusalNotice}

          <div className="mt-md flex flex-wrap gap-sm">
            <button type="submit" className="btn-danger px-md" disabled={pending}>
              {pending ? (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
              ) : (
                <CalendarX2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              {pending ? 'Cancelling this booking' : 'Yes, cancel this booking'}
            </button>
            <button
              type="button"
              className="btn-secondary px-md"
              disabled={pending}
              onClick={() => {
                setAsking(false)
                setRefusal(null)
              }}
            >
              <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              Keep the booking
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn-secondary mt-md px-md" onClick={() => setAsking(true)}>
          <CalendarX2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel this booking
        </button>
      )}
    </Card>
  )
}
