/**
 * The question SC-20 asks before every write.
 *
 * It says in words what is about to happen, and one press of the answer sends
 * one request. Both buttons are disabled while it is in flight, and a polite
 * status says it is under way. The question takes focus when it opens, so a
 * keyboard and a screen reader start from its first words.
 *
 * A 409 or a 403 shows the server's own sentence. A refusal that the form
 * behind the question cannot put under a field shows the server's sentence and
 * every message it sent. Anything else is the shared error state with a way to
 * try again.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import type { CounterRefusal } from '../counter/counter-refusal'

export function WriteQuestion({
  id,
  heading,
  children,
  answer,
  pendingAnswer,
  cancel,
  refusedTitle,
  pending,
  failure,
  onAnswer,
  onCancel,
}: {
  /** Unique on the page. The heading and the consequence are named from it. */
  id: string
  /** The question itself, for example "Hide the CP 100 from customers?". */
  heading: string
  /** What will happen, in words. */
  children: ReactNode
  /** The button that sends the write, for example "Yes, hide it". */
  answer: string
  /** The same button while the request is in flight. */
  pendingAnswer: string
  /** The button that puts the question away. */
  cancel: string
  /** The title of a notice that shows the server's sentence. */
  refusedTitle: string
  pending: boolean
  failure: CounterRefusal | null
  onAnswer: () => void
  onCancel: () => void
}) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const headingId = `${id}-heading`
  const consequenceId = `${id}-consequence`

  // The question opens in place of what was pressed, so focus goes to it.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  return (
    <section aria-labelledby={headingId} className="min-w-0 rounded-lg border-2 border-ink bg-surface p-md">
      <h3 id={headingId} ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold text-ink">
        {heading}
      </h3>
      <div id={consequenceId} className="mt-xs flex flex-col gap-xs break-words text-sm text-ink">
        {children}
      </div>
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={refusedTitle} error={failure.error} onRetry={onAnswer} />
        </div>
      )}
      {failure !== null && failure.kind !== 'fault' && (
        <div className="mt-md">
          <Notice tone="error" title={refusedTitle}>
            <p>{failure.detail}</p>
            {failure.kind === 'refused' && Object.keys(failure.fields).length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {Object.entries(failure.fields).map(([field, message]) => (
                  <li key={field}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="button"
          className="btn-primary px-md"
          disabled={pending}
          aria-describedby={consequenceId}
          onClick={onAnswer}
        >
          {pending ? pendingAnswer : answer}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={pending} onClick={onCancel}>
          {cancel}
        </button>
      </div>
      <p role="status" className="sr-only">
        {pending ? `${pendingAnswer}, please wait.` : ''}
      </p>
    </section>
  )
}
