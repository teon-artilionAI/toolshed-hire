/**
 * Deactivating and reactivating a staff account on SC-23, inside the account.
 *
 * Each asks first in a question of its own that says what is about to happen.
 * Deactivating asks why, because the reason is kept with the audit event, and
 * says that the person is signed out everywhere at once. Reactivating says
 * they can sign in again. One press of the answer sends one request, and both
 * buttons are disabled while it is in flight.
 *
 * The server refuses to deactivate the last active administrator, and refuses
 * an administrator who tries to deactivate their own account, each with a 409.
 * The browser does not guess at either. It sends the request and shows the
 * server's sentence. A 403 shows the server's sentence the same way, and a
 * refused reason shows its message under the box.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { deactivateStaffAccount, reactivateStaffAccount } from '../../shared/api/admin-users'
import type { AdminUser } from '../../shared/api/contract'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from '../counter/correction-model'
import { TextArea } from '../counter/counter-fields'
import { useUserWrite } from './use-user-write'

/** What a reason for a deactivation is read with later. */
const REASON_IS_READ_WITH = 'the audit trail'

export type AccessMove = 'deactivate' | 'reactivate'

interface AccessWords {
  question: string
  consequence: string
  answer: string
  pending: string
  refused: string
}

function accessWords(user: AdminUser, move: AccessMove): AccessWords {
  if (move === 'deactivate') {
    return {
      question: `Deactivate the account of ${user.fullName}?`,
      consequence: `${user.fullName} is signed out everywhere at once, on every device, and cannot sign in again until the account is reactivated. Their history stays on record.`,
      answer: 'Yes, deactivate it',
      pending: 'Deactivating it',
      refused: 'The account was not deactivated',
    }
  }
  return {
    question: `Reactivate the account of ${user.fullName}?`,
    consequence: `${user.fullName} can sign in again from now.`,
    answer: 'Yes, reactivate it',
    pending: 'Reactivating it',
    refused: 'The account was not reactivated',
  }
}

export function AccessQuestion({
  user,
  move,
  onDone,
  onCancel,
}: {
  user: AdminUser
  move: AccessMove
  /** Called with the account the server answered with. */
  onDone: (user: AdminUser) => void
  onCancel: () => void
}) {
  const words = accessWords(user, move)
  const write = useUserWrite(move === 'deactivate' ? 'staff_deactivated' : 'staff_reactivated', user.id)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const failure = write.failure
  const refusedReason = failure?.kind === 'refused' ? failure.fields.reason : undefined
  const otherRefusals = failure?.kind === 'refused' ? Object.entries(failure.fields).filter(([field]) => field !== 'reason') : []
  // A refusal of the reason alone is said under the box. Anything else the
  // server refused is said above the buttons, in its own words.
  const reasonOnly = failure?.kind === 'refused' && refusedReason !== undefined && otherRefusals.length === 0
  const id = `access-${move}`

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (move === 'reactivate') {
      write.send(() => reactivateStaffAccount(user.id), { onAnswer: onDone })
      return
    }
    const found = reasonProblem(reason, REASON_IS_READ_WITH)
    setProblem(found)
    if (found !== null) return
    const body = { reason: reason.trim() }
    write.send(() => deactivateStaffAccount(user.id, body), { onAnswer: onDone })
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
      {move === 'deactivate' && (
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
      )}
      {failure !== null && failure.kind !== 'fault' && !reasonOnly && (
        <div className="mt-md">
          <Notice tone="error" title={words.refused}>
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
          <ErrorState heading={words.refused} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button
          type="submit"
          className={move === 'deactivate' ? 'btn-danger px-md' : 'btn-primary px-md'}
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
