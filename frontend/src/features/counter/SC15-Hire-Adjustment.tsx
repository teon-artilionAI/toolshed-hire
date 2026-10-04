/**
 * The owner's adjustment of a hire on SC-15.
 *
 * It takes an amount including VAT, positive to charge the customer more and
 * negative to give money back, and a written reason. A settled hire is never
 * charged more, so on one the form only takes an amount that gives money back,
 * which the server refunds at once. Under them it says in
 * words what will be added, and the words follow the amount as it is typed.
 * The amount is the owner's own figure, written back as typed. Nothing is
 * worked out from it.
 *
 * One press sends one request to the adjustments route, and the button is
 * disabled while it is in flight. The answer is the hire as the server now
 * has it, with the new adjustment among its charges. A 422 puts the server's
 * message under the box it names, and a 409 or a 403 shows its sentence.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Scale } from 'lucide-react'
import type { Rental } from '../../shared/api/contract'
import { MAX_REASON_LENGTH, adjustHire } from '../../shared/api/corrections'
import { ErrorState } from '../../shared/async-states'
import { isNegativeMoney, money, unsignedMoney } from '../../shared/format'
import { Notice } from '../../shared/ui'
import { REASON_HELP, amountForTheWire, amountProblem, reasonProblem } from './correction-model'
import { ProblemList, TextInput } from './counter-fields'
import { useRentalWrite } from './use-rental-write'

const AMOUNT_ID = 'adjustment-amount'
const REASON_ID = 'adjustment-reason'
const HEADING_ID = 'adjustment-heading'

/** What the adjustment will add, in words, from the amount as typed. */
function adjustmentWords(typed: string, reference: string, hireSettled: boolean): string {
  const amount = amountForTheWire(typed)
  if (amount === null || amountProblem(typed, hireSettled) !== null) {
    return 'Enter the amount to see what will be added to the hire.'
  }
  const what = isNegativeMoney(amount)
    ? `gives ${unsignedMoney(amount)} back to the customer`
    : `charges the customer ${money(amount)} more`
  return `An adjustment that ${what}, including VAT, is added to ${reference} with your reason. The server then works the deposit and the balance out again.`
}

export function HireAdjustment({
  rental,
  onAdjusted,
  onCancel,
}: {
  rental: Rental
  /** Called with the hire the server answered with. */
  onAdjusted: (rental: Rental) => void
  onCancel: () => void
}) {
  const write = useRentalWrite(rental.id, 'adjustment')
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [tried, setTried] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const settled = rental.status === 'SETTLED'
  const failure = write.failure
  const server = failure?.kind === 'refused' ? failure.fields : {}
  const amountError = (tried ? amountProblem(amount, settled) : null) ?? server.amountIncVat
  const reasonError = (tried ? reasonProblem(reason) : null) ?? server.reason
  const problems = [
    ...(amountError === undefined || amountError === null ? [] : [{ id: AMOUNT_ID, message: amountError }]),
    ...(reasonError === undefined || reasonError === null ? [] : [{ id: REASON_ID, message: reasonError }]),
  ]
  const unplaced = failure?.kind === 'refused' && problems.length === 0 ? failure.detail : null

  // The form opens in place of its button, so focus goes to its heading.
  useEffect(() => {
    heading.current?.focus()
  }, [])

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTried(true)
    write.clearFailure()
    const wire = amountForTheWire(amount)
    if (amountProblem(amount, settled) !== null || reasonProblem(reason) !== null || wire === null) return
    const given = reason.trim()
    write.send(async () => {
      const answered = await adjustHire(rental.id, wire, given)
      onAdjusted(answered)
      return answered
    })
  }

  return (
    <form noValidate onSubmit={send} aria-labelledby={HEADING_ID} className="mt-md rounded-lg border-2 border-ink p-md">
      <h3 id={HEADING_ID} ref={heading} tabIndex={-1} className="text-base font-semibold text-ink">
        Adjust {rental.reference}
      </h3>
      {(problems.length > 0 || unplaced !== null) && (
        <div className="mt-sm">
          <Notice tone="error" title="Nothing has been added yet.">
            <ProblemList problems={problems} />
            {unplaced !== null && <p>{unplaced}</p>}
          </Notice>
        </div>
      )}
      <div className="mt-md grid gap-md sm:grid-cols-2">
        <TextInput
          id={AMOUNT_ID}
          label="Amount in rand, including VAT"
          help={
            settled
              ? 'For example -150.00 to give money back. The hire is settled, so it is never charged more.'
              : 'For example 150.00 to charge more, or -150.00 to give money back.'
          }
          inputMode="decimal"
          autoComplete="off"
          value={amount}
          onChange={setAmount}
          error={amountError ?? undefined}
          disabled={write.pending}
        />
        <TextInput
          id={REASON_ID}
          label="Why"
          help={REASON_HELP}
          value={reason}
          onChange={setReason}
          error={reasonError ?? undefined}
          disabled={write.pending}
          maxLength={MAX_REASON_LENGTH}
          autoComplete="off"
        />
      </div>
      <p className="mt-md rounded bg-muted p-sm text-sm text-ink" aria-live="polite">
        {adjustmentWords(amount, rental.reference, settled)}
      </p>
      {failure !== null && failure.kind !== 'fault' && failure.kind !== 'refused' && (
        <div className="mt-md">
          <Notice tone="error" title="The hire was not adjusted">
            <p>{failure.detail}</p>
          </Notice>
        </div>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <div className="mt-md">
          <ErrorState heading="We could not adjust the hire" error={failure.error} />
        </div>
      )}
      <div className="mt-md flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md" disabled={write.pending}>
          <Scale className="h-4 w-4 shrink-0" aria-hidden="true" />
          {write.pending ? 'Adding the adjustment' : 'Yes, add the adjustment'}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={write.pending} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Adding the adjustment, please wait.' : ''}
      </p>
    </form>
  )
}
