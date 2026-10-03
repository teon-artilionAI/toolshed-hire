/**
 * The no show on SC-11.
 *
 * Marking a customer as not having come is the one thing on the diary that
 * changes anything, and it cannot be taken back here, so it asks first. The
 * question asks for the reason, which the server keeps, and says in words what
 * the answer does. The units go back on the shelf and a strike is recorded
 * against the customer. Only then does one button send it.
 *
 * Whether it is offered at all is the server's answer, `canMarkNoShow`, for
 * the person asking and the moment the diary was read. What is shown after is
 * the server's answer too. A 409 means the booking moved on since the diary was
 * read, and the server's sentence says how.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { UserX } from 'lucide-react'
import type { DiaryCollection } from '../../shared/api/contract'
import { MAX_NO_SHOW_REASON_LENGTH } from '../../shared/api/reservations'
import { ErrorState } from '../../shared/async-states'
import { Notice, StatusPill } from '../../shared/ui'
import { TextInput } from './counter-fields'
import { DIARY_COLLECTION_LABEL } from './counter-labels'
import { useNoShow } from './use-no-show'

/** Said when the reason box is left empty. */
const REASON_NEEDED = 'Say why in a few words, so whoever reads this booking later knows.'

function unitsInWords(count: number): string {
  return count === 1 ? 'its unit goes' : `its ${count} units go`
}

export default function NoShowAction({ collection }: { collection: DiaryCollection }) {
  const { reservationId, reference, customerName } = collection
  const noShow = useNoShow(reservationId)
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonProblem, setReasonProblem] = useState<string | null>(null)
  const reasonRef = useRef<HTMLInputElement>(null)
  const askRef = useRef<HTMLButtonElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)
  const askedBefore = useRef(asking)

  // Opening the question puts the cursor in the reason box. Closing it puts
  // focus back on the button that opened it.
  useEffect(() => {
    if (askedBefore.current === asking) return
    askedBefore.current = asking
    if (asking) reasonRef.current?.focus()
    else askRef.current?.focus()
  }, [asking])

  // The answer replaces the question, so focus goes to the answer and is not
  // left on a button that is no longer there.
  useEffect(() => {
    if (noShow.reservation !== null) resultRef.current?.focus()
  }, [noShow.reservation])

  if (noShow.reservation !== null) {
    const answered = noShow.reservation
    return (
      <div ref={resultRef} tabIndex={-1} role="status" className="mt-sm rounded border-l-4 border-status-available bg-status-available-wash px-md py-sm">
        <p className="flex flex-wrap items-center gap-sm text-sm font-semibold text-ink">
          {answered.reference} is now
          <StatusPill
            status={answered.status}
            label={answered.status === 'NO_SHOW' ? DIARY_COLLECTION_LABEL.NO_SHOW : undefined}
          />
        </p>
        {answered.status === 'NO_SHOW' && (
          <p className="mt-xs text-sm text-ink">
            The units are back on the shelf and the strike is recorded against {answered.customerName}.
          </p>
        )}
      </div>
    )
  }

  if (!asking) {
    if (!collection.canMarkNoShow) return null
    return (
      <button ref={askRef} type="button" className="btn-secondary mt-sm px-md" onClick={() => setAsking(true)}>
        <UserX className="h-4 w-4 shrink-0" aria-hidden="true" />
        Mark as no show <span className="sr-only">{reference}</span>
      </button>
    )
  }

  function close() {
    noShow.clearFailure()
    setReasonProblem(null)
    setAsking(false)
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const given = reason.trim()
    if (given === '') {
      setReasonProblem(REASON_NEEDED)
      reasonRef.current?.focus()
      return
    }
    setReasonProblem(null)
    noShow.send(given)
  }

  const failure = noShow.failure
  const serverReasonProblem = failure?.kind === 'refused' ? (failure.fields.reason ?? failure.detail) : null
  const consequenceId = `no-show-consequence-${reservationId}`
  return (
    <form noValidate onSubmit={send} className="mt-sm flex flex-col gap-md rounded border border-line bg-muted p-md">
      <p id={consequenceId} className="text-sm text-ink">
        Marking {reference} as a no show means {unitsInWords(collection.unitCount)} back on the shelf for
        someone else, and a strike is recorded against {customerName}. Three strikes in twelve months put
        the account on hold.
      </p>
      <TextInput
        id={`no-show-reason-${reservationId}`}
        label="Why did the booking not go out?"
        value={reason}
        onChange={setReason}
        maxLength={MAX_NO_SHOW_REASON_LENGTH}
        help={`For example, did not arrive and did not answer the phone. Up to ${MAX_NO_SHOW_REASON_LENGTH} characters.`}
        error={reasonProblem ?? serverReasonProblem ?? undefined}
        disabled={noShow.pending}
        inputRef={reasonRef}
      />
      {failure !== null && (failure.kind === 'conflict' || failure.kind === 'forbidden' || failure.kind === 'accountOnHold') && (
        <Notice tone="error" title={`${reference} cannot be marked as a no show`}>
          <p>{failure.detail}</p>
        </Notice>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <ErrorState heading={`We could not mark ${reference} as a no show`} error={failure.error} />
      )}
      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-danger px-md" disabled={noShow.pending} aria-describedby={consequenceId}>
          {noShow.pending ? 'Marking it' : 'Yes, mark as no show'}
        </button>
        <button type="button" className="btn-secondary px-md" onClick={close} disabled={noShow.pending}>
          Keep the booking
        </button>
      </div>
    </form>
  )
}
