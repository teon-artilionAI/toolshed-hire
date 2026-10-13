/**
 * The question the trading calendar asks before it cancels a closure day.
 *
 * It names the branch, or every branch, and the day, and says that customers
 * can collect and bring equipment back that day again once it is open. Focus
 * moves to its heading. One press of the answer sends one request, and both
 * buttons are disabled while it is in flight. A 409, a 404 or a 403 shows the
 * server's sentence here. The closure is never deleted. Cancelling it keeps
 * the row with who cancelled it and when.
 */

import { useEffect, useRef } from 'react'
import { cancelClosureDay } from '../../shared/api/closure-days'
import type { CalendarClosedDay, ClosureDay } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { dayWords } from './calendar-words'
import { useClosureWrite } from './use-closure-write'

export function CancelQuestion({
  closure,
  closureId,
  branchLabel,
  onCancelled,
  onKeep,
}: {
  closure: CalendarClosedDay
  closureId: string
  /** The branch in words, or "Every branch". */
  branchLabel: string
  /** Called with the closure the server answered with, cancelled. */
  onCancelled: (closure: ClosureDay) => void
  onKeep: () => void
}) {
  const write = useClosureWrite('closure_cancelled', closureId)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const when = dayWords(closure.day)
  const id = `cancel-${closureId}`
  const where = closure.branchCode === null ? 'every branch' : branchLabel

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <div className="mt-sm min-w-0 rounded-lg border-2 border-ink bg-surface p-md">
      <h4 id={`${id}-heading`} ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold text-ink">
        Open {where} again on {when}?
      </h4>
      <p id={`${id}-consequence`} className="mt-xs break-words text-sm text-ink">
        Customers can choose that day to collect or bring equipment back once it is open again. The closure stays
        in the audit trail.
      </p>
      {failure !== null && failure.kind !== 'fault' && (
        <div className="mt-md">
          <Notice tone="error" title="The closure was not cancelled">
            <p className="break-words">{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading="We could not cancel the closure" error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="button"
          className="btn-primary px-md"
          disabled={write.pending}
          aria-describedby={`${id}-consequence`}
          onClick={() => write.send(() => cancelClosureDay(closureId), { onAnswer: onCancelled })}
        >
          {write.pending ? 'Cancelling the closure' : 'Yes, cancel the closure'}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={write.pending}
          onClick={() => {
            write.clearFailure()
            onKeep()
          }}
        >
          Keep it closed
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Cancelling the closure, please wait.' : ''}
      </p>
    </div>
  )
}
