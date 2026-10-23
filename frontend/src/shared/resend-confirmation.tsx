/**
 * The button that sends a booking confirmation again.
 *
 * The customer and the counter use the same control with a different request.
 * The answer says whether this environment can deliver email to the address.
 * When it cannot, the notice says the message was queued but this demonstration
 * only delivers to its own address, so the customer will not receive it. The
 * button is disabled while a request runs, and a refusal is shown with its
 * reference and a way to try again.
 */

import { useState } from 'react'
import { Mail } from 'lucide-react'
import type { ConfirmationResend } from './api/contract'
import { ErrorState } from './async-states'
import { Notice } from './ui'

type State =
  | { step: 'waiting' }
  | { step: 'sending' }
  | { step: 'sent'; emailDeliverable: boolean }
  | { step: 'failed'; error: unknown }

export function ResendConfirmation({
  bookingReference,
  onSend,
}: {
  bookingReference: string
  onSend: () => Promise<ConfirmationResend>
}) {
  const [state, setState] = useState<State>({ step: 'waiting' })

  async function send() {
    setState({ step: 'sending' })
    try {
      const answer = await onSend()
      setState({ step: 'sent', emailDeliverable: answer.emailDeliverable })
    } catch (error) {
      setState({ step: 'failed', error })
    }
  }

  return (
    <div className="flex flex-col gap-sm">
      <button
        type="button"
        className="btn-secondary px-md"
        onClick={() => void send()}
        disabled={state.step === 'sending'}
      >
        <Mail className="h-4 w-4 shrink-0" aria-hidden="true" />
        {state.step === 'sending' ? 'Sending the confirmation' : 'Send the confirmation again'}
      </button>
      <p role="status" className="text-sm text-slate-soft">
        {state.step === 'sending'
          ? `Asking the server to send booking ${bookingReference} again.`
          : state.step === 'sent'
            ? state.emailDeliverable
              ? `The confirmation for ${bookingReference} has been sent again.`
              : `The confirmation for ${bookingReference} was queued, but this demonstration only delivers email to its own address, so it will not reach the customer.`
            : 'Use this when the customer did not receive the confirmation.'}
      </p>
      {state.step === 'sent' && !state.emailDeliverable && (
        <Notice tone="warn" title="Restricted email">
          <p>
            The notification log records the attempt. In production, where the sender domain is
            verified, the customer would receive it.
          </p>
        </Notice>
      )}
      {state.step === 'failed' && (
        <ErrorState
          heading="We could not send the confirmation again"
          error={state.error}
          onRetry={() => void send()}
        />
      )}
    </div>
  )
}
