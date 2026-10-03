/**
 * The payment of a balance on SC-15, when the deposit did not cover the
 * charges.
 *
 * The customer pays the balance at the counter and the assistant records the
 * reference of the payment, 1 to 40 characters. The payment is simulated, so
 * nothing reaches a bank, and the screen says so. One press sends one request,
 * and the button is disabled while it is in flight. The answer is the hire as
 * the server now has it, settled.
 *
 * A 409 means nothing is due any more, and a 403 that the hire is not at this
 * branch. Both show the server's sentence. A refused reference shows the
 * server's message under the box.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Banknote } from 'lucide-react'
import type { Rental } from '../../shared/api/contract'
import { MAX_PAYMENT_REFERENCE_LENGTH, payBalance } from '../../shared/api/rentals'
import { ErrorState } from '../../shared/async-states'
import { money } from '../../shared/format'
import { Notice } from '../../shared/ui'
import { TextInput } from './counter-fields'
import { useRentalWrite } from './use-rental-write'

const REFERENCE_ID = 'balance-payment-reference'

/** Said when the box is left empty. */
const REFERENCE_NEEDED = 'Enter the reference of the payment, as it is on the slip.'

export function BalancePayment({ rental, onPaid }: { rental: Rental; onPaid: (rental: Rental) => void }) {
  const write = useRentalWrite(rental.id, 'balance_payment')
  const [reference, setReference] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const failure = write.failure
  const serverProblem = failure?.kind === 'refused' ? (failure.fields.paymentReference ?? failure.detail) : null

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const given = reference.trim()
    if (given === '') {
      setProblem(REFERENCE_NEEDED)
      return
    }
    if (given.length > MAX_PAYMENT_REFERENCE_LENGTH) {
      setProblem(`Keep the reference to ${MAX_PAYMENT_REFERENCE_LENGTH} characters. This has ${given.length}.`)
      return
    }
    setProblem(null)
    write.send(async () => {
      const paid = await payBalance(rental.id, given)
      onPaid(paid)
      return paid
    })
  }

  return (
    <form noValidate onSubmit={send} aria-label="Pay the balance" className="flex flex-col gap-md">
      <TextInput
        id={REFERENCE_ID}
        label="Payment reference"
        help={`Up to ${MAX_PAYMENT_REFERENCE_LENGTH} characters. The payment is simulated, so nothing reaches a bank.`}
        value={reference}
        onChange={setReference}
        error={problem ?? serverProblem ?? undefined}
        disabled={write.pending}
        maxLength={MAX_PAYMENT_REFERENCE_LENGTH}
        autoComplete="off"
      />
      {failure !== null && (failure.kind === 'conflict' || failure.kind === 'forbidden' || failure.kind === 'accountOnHold') && (
        <Notice tone="error" title="The payment was not recorded">
          <p>{failure.detail}</p>
        </Notice>
      )}
      {failure !== null && failure.kind === 'fault' && (
        <ErrorState heading="We could not record the payment" error={failure.error} />
      )}
      <div>
        <button type="submit" className="btn-primary px-lg" disabled={write.pending}>
          <Banknote className="h-4 w-4 shrink-0" aria-hidden="true" />
          {write.pending ? 'Recording the payment' : `Record the payment of ${money(rental.balanceDue)}`}
        </button>
      </div>
      <p role="status" className="sr-only">
        {write.pending ? 'Recording the payment, please wait.' : ''}
      </p>
    </form>
  )
}
