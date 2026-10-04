/**
 * The owner's question before waiving or reversing one charge on SC-15.
 *
 * It says in words what is about to happen and asks for the reason, which the
 * server keeps with the charge and in the audit trail. A waiver takes a
 * pending charge off what is owed and keeps it on the hire as waived. A
 * reversal leaves a settled charge as it is and adds a new one for the same
 * amount the other way, pointing back at it. Either way the server works the
 * deposit and the balance out again, and the screen shows the hire it
 * answers with.
 *
 * One press of the answer sends one request, and it is disabled while it is in
 * flight. A refused reason shows the server's message under the box. A 409,
 * such as a charge that moved on since the hire was read, or a 403 shows the
 * server's sentence, and the hire is read again.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { Rental, RentalCharge } from '../../shared/api/contract'
import { MAX_REASON_LENGTH, reverseCharge, waiveCharge } from '../../shared/api/corrections'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import { REASON_HELP, reasonProblem } from './correction-model'
import { TextInput } from './counter-fields'
import { CHARGE_NOUN, amountWords } from './counter-labels'
import { useRentalWrite } from './use-rental-write'

/** The two corrections of one charge. */
export type ChargeCorrectionKind = 'waiver' | 'reversal'

const QUESTION: Record<ChargeCorrectionKind, { verb: string; answer: string; pending: string; refused: string }> = {
  waiver: { verb: 'Waive', answer: 'Yes, waive it', pending: 'Waiving it', refused: 'The charge was not waived' },
  reversal: { verb: 'Reverse', answer: 'Yes, reverse it', pending: 'Reversing it', refused: 'The charge was not reversed' },
}

/** What the correction will do, in words. */
function consequence(kind: ChargeCorrectionKind, rental: Rental, charge: RentalCharge): string {
  const noun = CHARGE_NOUN[charge.type]
  const settles = 'The server then works the deposit and the balance out again.'
  if (kind === 'waiver') {
    return `The ${noun} of ${amountWords(charge.amountIncVat)} stops being owed. It stays on ${rental.reference} marked as waived, with your reason. ${settles}`
  }
  return `A new ${noun} for the same amount the other way is added to ${rental.reference}, with your reason, and points back at this one. This charge stays on the hire as it is. ${settles}`
}

export function ChargeCorrection({
  rental,
  charge,
  kind,
  onCorrected,
  onCancel,
}: {
  rental: Rental
  charge: RentalCharge
  kind: ChargeCorrectionKind
  /** Called with the hire the server answered with. */
  onCorrected: (rental: Rental) => void
  onCancel: () => void
}) {
  const write = useRentalWrite(rental.id, kind)
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const reasonRef = useRef<HTMLInputElement>(null)
  const failure = write.failure
  const serverProblem = failure?.kind === 'refused' ? (failure.fields.reason ?? failure.detail) : null
  const words = QUESTION[kind]
  const headingId = `correct-${charge.id}`
  const consequenceId = `correct-${charge.id}-consequence`

  // The question opens in place of its button, so focus goes to its heading.
  useEffect(() => {
    heading.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = reasonProblem(reason)
    setProblem(found)
    if (found !== null) {
      reasonRef.current?.focus()
      return
    }
    const given = reason.trim()
    write.send(async () => {
      const answered = await (kind === 'waiver' ? waiveCharge(charge.id, given) : reverseCharge(charge.id, given))
      onCorrected(answered)
      return answered
    })
  }

  return (
    <form noValidate onSubmit={send} aria-labelledby={headingId} className="mt-md rounded-lg border-2 border-ink p-md">
      <h4 id={headingId} ref={heading} tabIndex={-1} className="text-base font-semibold text-ink">
        {words.verb} the {CHARGE_NOUN[charge.type]} of {amountWords(charge.amountIncVat)}?
      </h4>
      <p id={consequenceId} className="mt-xs break-words text-sm text-ink">
        {consequence(kind, rental, charge)}
      </p>
      <div className="mt-md">
        <TextInput
          id={`correct-${charge.id}-reason`}
          label="Why"
          help={REASON_HELP}
          value={reason}
          onChange={setReason}
          error={problem ?? serverProblem ?? undefined}
          disabled={write.pending}
          maxLength={MAX_REASON_LENGTH}
          autoComplete="off"
          inputRef={reasonRef}
        />
      </div>
      {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
        <div className="mt-md">
          <Notice tone="error" title={words.refused}>
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading={`We could not ${words.verb.toLowerCase()} the charge`} error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md" disabled={write.pending} aria-describedby={consequenceId}>
          {write.pending ? words.pending : words.answer}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={write.pending} onClick={onCancel}>
          Keep it as it is
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? `${words.pending}, please wait.` : ''}
      </p>
    </form>
  )
}
