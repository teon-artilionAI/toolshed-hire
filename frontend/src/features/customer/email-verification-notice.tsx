/**
 * What SC-09 says to an account whose email address is not confirmed yet.
 *
 * A hire cannot be confirmed online until the address is. The notice says so
 * and offers to send the link again. That is one request for each press of
 * the button, and the button is disabled while it is in flight.
 *
 * The API answers the same way whether or not it sent anything, and says
 * whether an email can reach the address at all. When it cannot, the notice
 * says that in plain words, with what the person can do instead.
 *
 * The session says the same of the account's address before anything is
 * sent. When this environment cannot deliver to it, the notice does not ask
 * the person to open a link that never reached them.
 */

import { useRef, useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { VERIFICATION_LINK_HOURS, resendVerification } from '../../shared/api/account'
import type { EmailDelivery } from '../../shared/api/contract'
import { Notice } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { describeAccountFailure } from './account-failure'
import type { AccountFailure } from './account-failure'
import { AccountFailureNotice } from './account-failure-notice'
import { DEMONSTRATION_EMAIL_REASON, DemonstrationEmailNote, WITHOUT_THE_LINK } from './email-delivery-note'

export const EMAIL_UNCONFIRMED_TITLE = 'Your email address has not been confirmed'
export const LINK_SENT_AGAIN_TITLE = 'We have sent the link again'

/** @param email The address on the account, which is where the link goes. */
export function EmailVerificationNotice({ email }: { email: string }) {
  const { user } = useSession()
  const reachable = user?.emailDeliverable === true
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<EmailDelivery | null>(null)
  const [failure, setFailure] = useState<AccountFailure | null>(null)
  const inFlight = useRef(false)

  async function sendAgain(): Promise<void> {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setSent(null)
    setFailure(null)
    try {
      setSent(await resendVerification())
    } catch (cause) {
      setFailure(describeAccountFailure(cause))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-sm">
      <Notice tone="warn" title={EMAIL_UNCONFIRMED_TITLE}>
        {reachable ? (
          <p>
            A hire cannot be confirmed online until it is. Open the link we sent to{' '}
            <span className="break-all font-medium">{email}</span>, or send it again.
          </p>
        ) : (
          <p>
            A hire cannot be confirmed online until it is. {DEMONSTRATION_EMAIL_REASON} {WITHOUT_THE_LINK}
          </p>
        )}
        <button
          type="button"
          className="btn-secondary mt-sm px-md"
          disabled={busy}
          onClick={() => void sendAgain()}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {busy ? 'Sending the link' : 'Send the link again'}
        </button>
      </Notice>

      {sent?.emailDeliverable === true && (
        <Notice tone="success" title={LINK_SENT_AGAIN_TITLE}>
          <p>Open it within {VERIFICATION_LINK_HOURS} hours. An older link no longer works.</p>
        </Notice>
      )}
      {sent?.emailDeliverable === false && (
        <DemonstrationEmailNote>{WITHOUT_THE_LINK}</DemonstrationEmailNote>
      )}
      {failure && (
        <AccountFailureNotice
          failure={failure}
          refusedTitle="We could not send the link"
          faultHeading="We could not send the link"
          onRetry={() => void sendAgain()}
        />
      )}
    </div>
  )
}
