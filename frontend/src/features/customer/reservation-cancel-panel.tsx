/**
 * Cancelling a booking, and explaining why sometimes you cannot.
 *
 * A refusal that only says no is useless to someone whose job has been
 * rained off. So every state that cannot be cancelled says which rule
 * applies and what to do instead. The rule itself is simple: a booking can
 * be cancelled until the equipment leaves the branch, and after that it is
 * a return, not a cancellation.
 */

import { useState } from 'react'
import type { ReactNode } from 'react'
import { CalendarX2, Undo2 } from 'lucide-react'
import { money } from '../../shared/format'
import type { Branch, Reservation, ReservationStatus } from '../../shared/types'
import { Card, Notice } from '../../shared/ui'
import { CANCELLABLE_STATUSES } from './customer-labels'
import { depositTotal } from './reservation-maths'

const CANCELLATION_REASONS = [
  'The job has been postponed',
  'The job is not going ahead',
  'I booked the wrong dates',
  'I need different equipment',
  'I found it closer to site',
  'Another reason',
]

function Alternatives({ children }: { children: ReactNode }) {
  return <div className="mt-md text-sm text-slate-soft">{children}</div>
}

/** The message shown when the booking is past the point of cancelling. */
function BlockedNotice({
  status,
  branch,
}: {
  status: ReservationStatus
  branch: Branch
}) {
  if (status === 'COLLECTED') {
    return (
      <>
        <Notice tone="warn" title="This hire has already been collected">
          <p>
            Bookings can be cancelled up until the equipment leaves the branch.
            This one is out with you, so there is nothing left to cancel. What
            you need now is a return.
          </p>
        </Notice>
        <Alternatives>
          <p>Two things you can do instead.</p>
          <ul className="mt-sm list-disc pl-lg">
            <li>
              Bring the equipment back to {branch.name} in {branch.suburb} to
              close the hire and release what is left of your deposit.
            </li>
            <li>
              Ask the counter at {branch.name} to extend the hire if you need
              the equipment for longer. Extending stops the late fee, returning
              late does not.
            </li>
          </ul>
        </Alternatives>
      </>
    )
  }

  if (status === 'CLOSED') {
    return (
      <Notice tone="info" title="This hire is finished">
        <p>
          Everything was returned and the account was settled, so there is
          nothing to cancel. The charges are on your account screen if you need
          them.
        </p>
      </Notice>
    )
  }

  if (status === 'CANCELLED') {
    return (
      <Notice tone="info" title="This booking is already cancelled">
        <p>
          Nothing further is owed on it. Book again whenever the job is back
          on.
        </p>
      </Notice>
    )
  }

  if (status === 'NO_SHOW') {
    return (
      <>
        <Notice tone="warn" title="This booking was not collected">
          <p>
            The equipment was held for the collection day and then released to
            other customers, so the booking closed itself. There is nothing
            left to cancel.
          </p>
        </Notice>
        <Alternatives>
          <p>
            Repeated no-shows put an account on hold, which stops new bookings
            until the branch lifts it. Speak to {branch.name} if that has
            happened to you.
          </p>
        </Alternatives>
      </>
    )
  }

  return (
    <Notice tone="info" title="This booking has expired">
      <p>
        A hold only lasts until the collection date. This one ran out, so the
        equipment went back into stock and there is nothing to cancel.
      </p>
    </Notice>
  )
}

export function CancellationPanel({
  reservation,
  status,
  branch,
  onCancel,
}: {
  reservation: Reservation
  /** The status as the screen currently sees it, which may already have
   *  been changed by a cancellation in this session. */
  status: ReservationStatus
  branch: Branch
  onCancel: (reason: string) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | undefined>()

  if (!CANCELLABLE_STATUSES.includes(status)) {
    return (
      <Card title="Cancelling this booking">
        <BlockedNotice status={status} branch={branch} />
      </Card>
    )
  }

  function confirmCancellation() {
    if (!reason) {
      setError('Choose a reason so the branch knows what to free up.')
      return
    }
    onCancel(reason)
  }

  return (
    <Card title="Cancelling this booking">
      <p className="text-sm text-slate-soft">
        You can cancel any time before you collect. The{' '}
        {money(depositTotal(reservation))} deposit is only taken at the
        counter when the equipment is handed over, so cancelling now costs you
        nothing.
      </p>

      {confirming ? (
        <div className="mt-md rounded-lg border border-line bg-muted p-md">
          <h3 className="text-base font-semibold text-ink">
            Cancel {reservation.reference}?
          </h3>
          <p className="mt-xs text-sm text-slate-soft">
            The equipment goes back into stock straight away and someone else
            can book it. This cannot be undone.
          </p>

          <div className="mt-md">
            <label className="field-label" htmlFor="cancel-reason">
              Why are you cancelling?
            </label>
            <select
              id="cancel-reason"
              className={`field-input cursor-pointer ${error ? 'border-status-overdue' : ''}`}
              value={reason}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'cancel-reason-error' : undefined}
              onChange={(event) => {
                setReason(event.target.value)
                setError(undefined)
              }}
            >
              <option value="">Choose a reason</option>
              {CANCELLATION_REASONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            {error && (
              <p className="field-error" id="cancel-reason-error">
                <span>{error}</span>
              </p>
            )}
          </div>

          <div className="mt-md flex flex-wrap gap-sm">
            <button
              type="button"
              className="btn-danger px-md"
              onClick={confirmCancellation}
            >
              <CalendarX2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              Yes, cancel this booking
            </button>
            <button
              type="button"
              className="btn-secondary px-md"
              onClick={() => {
                setConfirming(false)
                setError(undefined)
              }}
            >
              <Undo2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              Keep the booking
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="btn-secondary mt-md px-md"
          onClick={() => setConfirming(true)}
        >
          <CalendarX2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel this booking
        </button>
      )}
    </Card>
  )
}
