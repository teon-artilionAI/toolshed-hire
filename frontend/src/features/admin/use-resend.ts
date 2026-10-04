/**
 * Sending a failed booking confirmation again, as one request.
 *
 * It is sent once for each press of the button, and a second press while it is
 * in flight does nothing. It is never repeated by itself, because a request
 * that timed out may still have reached the server and queued a second email.
 *
 * The server answers with the new email and leaves the failed one as it was,
 * so both are in the log. The log and the trail are then marked out of date,
 * and the page on the screen is read again with the new attempt on it. A 409
 * means the email did not fail after all, so the log is read again for that
 * too.
 */

import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { forgetTheLog } from '../../shared/api/admin-queries'
import { resendNotification } from '../../shared/api/audit-log'
import type { EmailNotification } from '../../shared/api/contract'
import { logEvent } from '../../shared/api/log'
import { describeCounterFailure } from '../counter/counter-refusal'
import type { CounterRefusal } from '../counter/counter-refusal'

export interface Resend {
  /** True while the request is in flight. */
  pending: boolean
  /** The new email the server queued, once it has. */
  sent: EmailNotification | null
  /** Why the last request did not work, until the next one starts. */
  failure: CounterRefusal | null
  send: () => void
  /** Put the failure away, when the person closes the question. */
  clearFailure: () => void
}

/** @param notificationId The key of the email that failed. */
export function useResend(notificationId: string): Resend {
  const queryClient = useQueryClient()
  const [pending, setPending] = useState(false)
  const [sent, setSent] = useState<EmailNotification | null>(null)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  async function send(): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setPending(true)
    setFailure(null)
    try {
      const answered = await resendNotification(notificationId)
      logEvent('info', 'admin.notification_resent', {
        failed_notification: notificationId,
        new_notification: answered.id,
        reservation: answered.reservationReference,
        status: answered.status,
      })
      setSent(answered)
      forgetTheLog(queryClient)
    } catch (cause) {
      const refusal = describeCounterFailure(cause)
      logEvent('warn', 'admin.notification_resend_refused', { notification: notificationId, refusal: refusal.kind })
      if (refusal.kind === 'conflict') forgetTheLog(queryClient)
      setFailure(refusal)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return {
    pending,
    sent,
    failure,
    send: () => void send(),
    clearFailure: () => setFailure(null),
  }
}
