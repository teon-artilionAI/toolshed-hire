/**
 * The question the trading calendar asks before it closes a day.
 *
 * It names the branch, or every branch, the day and the reason, and lists
 * every held or confirmed booking that starts or ends on that day, with the
 * customer's name and number, or says there are none. It says plainly that
 * closing the day does not cancel those bookings, and that the owner rings
 * each customer to agree another day. Focus moves to its heading, so a screen
 * reader hears the question first.
 *
 * One press of the answer sends one request, and both buttons are disabled
 * while it is in flight. A refused field goes back to the form, under the
 * field it names. A 409 or a 403 shows the server's sentence here.
 */

import { useEffect, useRef } from 'react'
import { addClosureDay } from '../../shared/api/closure-days'
import type { ClosureDay, ClosureImpact, StrandedBooking } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ErrorState } from '../../shared/async-states'
import { formatDateShort } from '../../shared/format'
import { Notice } from '../../shared/ui'
import { HIRE_DAY_WORDS, dayWords, impactLine } from './calendar-words'
import { useClosureWrite } from './use-closure-write'

const QUESTION_ID = 'closure-question'

/** What the owner asked to close, already checked by the form. */
export interface ClosureAsked {
  branchCode: string | null
  /** The branch in words, or "Every branch". */
  branchLabel: string
  day: string
  reason: string
}

function Booking({ booking, everyBranch }: { booking: StrandedBooking; everyBranch: boolean }) {
  return (
    <li className="min-w-0 rounded border border-line p-sm">
      <p className="break-words text-sm font-semibold text-ink">
        {booking.customerName}{' '}
        <a href={`tel:${booking.customerPhone.replace(/\s+/g, '')}`} className="font-normal underline">
          {booking.customerPhone}
        </a>
      </p>
      <p className="break-words text-sm text-slate-soft">
        <span className="font-mono">{booking.reference}</span>, {formatDateShort(booking.from)} to{' '}
        {formatDateShort(booking.to)}
        {everyBranch ? `, at ${booking.branchCode}` : ''}. {HIRE_DAY_WORDS[booking.hireDay]}.
      </p>
    </li>
  )
}

export function ClosureQuestion({
  asked,
  impact,
  onClosed,
  onRefused,
  onBack,
}: {
  asked: ClosureAsked
  impact: ClosureImpact
  /** Called with the closure the server answered with. */
  onClosed: (closure: ClosureDay) => void
  /** Called with the fields the server refused, to show them on the form. */
  onRefused: (fields: FieldErrors) => void
  onBack: () => void
}) {
  const write = useClosureWrite('closure_added', 'new')
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const when = dayWords(asked.day)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function close() {
    const body = { branchCode: asked.branchCode, day: asked.day, reason: asked.reason }
    write.send(() => addClosureDay(body), { onAnswer: onClosed, onRefused })
  }

  return (
    <section aria-labelledby={`${QUESTION_ID}-heading`} className="min-w-0 rounded-lg border-2 border-ink bg-surface p-md">
      <h3 id={`${QUESTION_ID}-heading`} ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold text-ink">
        Close {asked.branchCode === null ? 'every branch' : asked.branchLabel} on {when}?
      </h3>
      <dl className="mt-xs text-sm">
        <dt className="text-slate-soft">The reason customers read</dt>
        <dd className="break-words text-ink">{asked.reason}</dd>
      </dl>
      <h4 className="mt-md text-sm font-semibold text-ink">Bookings on that day</h4>
      <p id={`${QUESTION_ID}-impact`} className="mt-xs text-sm text-ink">
        {impactLine(impact)}
      </p>
      {impact.items.length > 0 && (
        <>
          <ul className="mt-sm flex flex-col gap-sm" aria-label="Bookings that start or end on that day">
            {impact.items.map((booking) => (
              <Booking key={booking.reference} booking={booking} everyBranch={asked.branchCode === null} />
            ))}
          </ul>
          <p id={`${QUESTION_ID}-consequence`} className="mt-sm text-sm text-ink">
            Closing the day does not cancel these bookings. Ring each customer to agree another day, and change
            the booking at the counter.
          </p>
        </>
      )}
      {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
        <div className="mt-md">
          <Notice tone="error" title={`${when} was not closed`}>
            <p className="break-words">{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={`We could not close ${when}`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="button"
          className="btn-danger px-md"
          disabled={write.pending}
          aria-describedby={`${QUESTION_ID}-impact`}
          onClick={close}
        >
          {write.pending ? 'Closing the day' : 'Yes, close the day'}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={write.pending}
          onClick={() => {
            write.clearFailure()
            onBack()
          }}
        >
          Go back and change it
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Closing the day, please wait.' : ''}
      </p>
    </section>
  )
}
