/**
 * A booking request that did not work, in front of the person.
 *
 * booking-refusal.ts sorts a failure into one of five answers, and this draws
 * four of them. A conflict and a refusal show the server's own sentence. An
 * unverified email address is said plainly, in words written here, because
 * the person has to act on it somewhere else. A fault is the shared error
 * state with a way to try again.
 *
 * The fifth, an account on hold, is not drawn here. It outlasts the request
 * that found it, so each view shows it for as long as the screen is open and
 * takes its buttons away. That is `AccountOnHoldNotice`.
 */

import type { ReactNode } from 'react'
import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import type { BookingRefusal } from './booking-refusal'

export function EmailNotVerifiedNotice() {
  return (
    <Notice tone="warn" title="Your email address has not been verified">
      <p>
        This hire cannot be confirmed online until the email address on your account has been
        verified. Ring your branch and they can confirm it for you while the equipment is still
        held.
      </p>
    </Notice>
  )
}

/** @param because The server's sentence about why the account may not book. */
export function AccountOnHoldNotice({ because }: { because: string }) {
  return (
    <Notice tone="error" title="Your account cannot book at the moment">
      <p>{because}</p>
    </Notice>
  )
}

export function BookingRefusalNotice({
  refusal,
  conflictTitle,
  refusedTitle = 'We cannot book those details',
  faultHeading,
  otherMessages = [],
  onRetry,
  children,
}: {
  refusal: BookingRefusal
  /** The heading over the server's sentence when the answer was a 409. */
  conflictTitle: string
  /** The heading over the server's sentence when the answer was a 422. */
  refusedTitle?: string
  /** The whole heading when the request failed some other way. */
  faultHeading: string
  /** Messages about fields the view has no input for. */
  otherMessages?: readonly string[]
  onRetry: () => void
  /** Ways forward, shown under the server's sentence. */
  children?: ReactNode
}) {
  if (refusal.kind === 'accountOnHold') return null
  if (refusal.kind === 'emailNotVerified') return <EmailNotVerifiedNotice />
  if (refusal.kind === 'fault') {
    return (
      <ErrorState heading={faultHeading} error={refusal.error} onRetry={onRetry}>
        {children}
      </ErrorState>
    )
  }
  return (
    <Notice tone="error" title={refusal.kind === 'conflict' ? conflictTitle : refusedTitle}>
      <p>{refusal.detail}</p>
      {otherMessages.length > 0 && (
        <ul className="mt-xs list-disc pl-lg">
          {otherMessages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      {children && <div className="mt-sm flex flex-wrap gap-sm">{children}</div>}
    </Notice>
  )
}
