/**
 * The question SC-23 asks before it moves a customer's standing.
 *
 * It names the move, says what it does to the customer's bookings, and asks
 * why, because the reason is kept with the audit event. Releasing a hold says
 * that the count of bookings the customer did not collect is kept, with the
 * server's count. One press of the answer sends one request, and both buttons
 * are disabled while it is in flight.
 *
 * A 409 or a 403 shows the server's sentence. A refused reason shows its
 * message under the box, and any other refusal is said above the buttons.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { setCustomerStanding } from '../../shared/api/admin-customers'
import type { AccountStatus, CustomerSummary } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from '../counter/correction-model'
import { TextArea } from '../counter/counter-fields'
import { standingMoveWords } from './staff-words'
import { useUserWrite } from './use-user-write'

/** What a reason for a move is read with later. */
const REASON_IS_READ_WITH = 'the audit trail'

export function StandingQuestion({
  customer,
  to,
  onMoved,
  onCancel,
}: {
  customer: CustomerSummary
  to: AccountStatus
  /** Called with the customer the server answered with. */
  onMoved: (customer: CustomerSummary) => void
  onCancel: () => void
}) {
  const words = standingMoveWords(customer, to)
  const write = useUserWrite('customer_standing_set', customer.id)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const refusedReason = failure?.kind === 'refused' ? failure.fields.reason : undefined
  const otherRefusals = failure?.kind === 'refused' ? Object.entries(failure.fields).filter(([field]) => field !== 'reason') : []
  const reasonOnly = failure?.kind === 'refused' && refusedReason !== undefined && otherRefusals.length === 0
  const id = `standing-${customer.id}-${to}`

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = reasonProblem(reason, REASON_IS_READ_WITH)
    setProblem(found)
    if (found !== null) return
    const body = { accountStatus: to, reason: reason.trim() }
    write.send(() => setCustomerStanding(customer.id, body), { onAnswer: onMoved })
  }

  return (
    <form
      noValidate
      onSubmit={send}
      aria-labelledby={`${id}-heading`}
      className="min-w-0 rounded-lg border-2 border-ink bg-surface p-md"
    >
      <h4 id={`${id}-heading`} ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold text-ink">
        {words.question}
      </h4>
      <p id={`${id}-consequence`} className="mt-xs break-words text-sm text-ink">
        {words.consequence}
      </p>
      <div className="mt-md">
        <TextArea
          id={`${id}-reason`}
          label="Why"
          help={REASON_HELP}
          value={reason}
          onChange={(value) => {
            setReason(value)
            setProblem(null)
          }}
          error={problem ?? refusedReason}
          disabled={write.pending}
          rows={2}
        />
      </div>
      {failure !== null && failure.kind !== 'fault' && !reasonOnly && (
        <div className="mt-md">
          <Notice tone="error" title={`The standing of ${customer.displayName} was not changed`}>
            <p className="break-words">{failure.detail}</p>
            {otherRefusals.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {otherRefusals.map(([field, message]) => (
                  <li key={field}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={`We could not change the standing of ${customer.displayName}`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="submit"
          className={to === 'ACTIVE' ? 'btn-primary px-md' : 'btn-danger px-md'}
          disabled={write.pending}
          aria-describedby={`${id}-consequence`}
        >
          {write.pending ? words.pending : words.answer}
        </button>
        <button
          type="button"
          className="btn-secondary px-md"
          disabled={write.pending}
          onClick={() => {
            write.clearFailure()
            onCancel()
          }}
        >
          Leave it as it is
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? `${words.pending}, please wait.` : ''}
      </p>
    </form>
  )
}
