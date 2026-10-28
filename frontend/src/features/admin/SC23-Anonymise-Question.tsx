/**
 * The question SC-23 asks before it removes a customer's personal details.
 *
 * It says what is removed, what stays and that it cannot be undone, and asks
 * why, because the reason is kept with the audit event. One press of the
 * answer sends one request, and both buttons are disabled while it is in
 * flight.
 *
 * A 409 or a 403 shows the server's sentence, which says what is still open
 * when that is why. A refused reason shows its message under the box, and any
 * other refusal is said above the buttons.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { anonymiseCustomer } from '../../shared/api/admin-customers'
import type { CustomerSummary } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from '../counter/correction-model'
import { TextArea } from '../counter/counter-fields'
import { anonymiseWords } from './staff-words'
import { useUserWrite } from './use-user-write'

/** What a reason for removing the details is read with later. */
const REASON_IS_READ_WITH = 'the audit trail'

export function AnonymiseQuestion({
  customer,
  onAnonymised,
  onCancel,
}: {
  customer: CustomerSummary
  /** Called with the customer the server answered with. */
  onAnonymised: (customer: CustomerSummary) => void
  onCancel: () => void
}) {
  const words = anonymiseWords(customer)
  const write = useUserWrite('customer_anonymised', customer.id)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const refusedReason = failure?.kind === 'refused' ? failure.fields.reason : undefined
  const otherRefusals = failure?.kind === 'refused' ? Object.entries(failure.fields).filter(([field]) => field !== 'reason') : []
  const reasonOnly = failure?.kind === 'refused' && refusedReason !== undefined && otherRefusals.length === 0
  const id = `anonymise-${customer.id}`

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = reasonProblem(reason, REASON_IS_READ_WITH)
    setProblem(found)
    if (found !== null) return
    const body = { reason: reason.trim() }
    write.send(() => anonymiseCustomer(customer.id, body), { onAnswer: onAnonymised })
  }

  return (
    <form
      noValidate
      onSubmit={send}
      aria-labelledby={`${id}-heading`}
      className="min-w-0 rounded-lg border-2 border-ink bg-surface p-md"
    >
      <h4 id={`${id}-heading`} ref={headingRef} tabIndex={-1} className="wrap-break-word text-base font-semibold text-ink">
        {words.question}
      </h4>
      <div id={`${id}-consequence`} className="mt-xs text-sm text-ink">
        <p className="wrap-break-word">{words.removed}</p>
        <p className="mt-xs wrap-break-word">{words.kept}</p>
        <p className="mt-xs font-semibold">{words.final}</p>
      </div>
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
          <Notice tone="error" title={`The personal details of ${customer.displayName} were not removed`}>
            <p className="wrap-break-word">{failure.detail}</p>
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
          <ErrorState heading={`We could not remove the personal details of ${customer.displayName}`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-danger px-md" disabled={write.pending} aria-describedby={`${id}-consequence`}>
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
          {words.keep}
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? `${words.pending}, please wait.` : ''}
      </p>
    </form>
  )
}
