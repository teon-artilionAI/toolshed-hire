/**
 * Where a verification link lands, on SC-05.
 *
 * The link in the email opens `/register#verify=<token>`. The screen takes the
 * token out of the address and hands it here. This posts it once and shows
 * what the API said. Either the address is confirmed, or the link is no longer
 * good, which is one answer for a link that is unknown, already used or more
 * than a day old.
 *
 * The token is dropped as soon as the API has answered for it. It is kept only
 * while a request that could not be made is waiting to be tried again.
 *
 * A new link cannot be asked for from here, because that needs a signed in
 * account. So the way forward from a dead link is to sign in and send the
 * link again from the account screen.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  VERIFICATION_LINK_HOURS,
  VERIFICATION_LINK_INVALID,
  verifyEmail,
} from '../../shared/api/account'
import { LoadingState } from '../../shared/async-states'
import { ACCOUNT_PATH, SIGN_IN_PATH } from '../../shared/navigation'
import { signInAddress } from '../../shared/screen-access'
import { Card } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { describeAccountFailure } from './account-failure'
import type { AccountFailure } from './account-failure'
import { AccountFailureNotice } from './account-failure-notice'
import { StateHeading } from './state-heading'

export const VERIFICATION_CONFIRMED_HEADING = 'Your email address is confirmed'
export const VERIFICATION_INVALID_HEADING = 'That link no longer works'

type VerificationState =
  | { kind: 'checking' }
  | { kind: 'confirmed' }
  | { kind: 'invalid' }
  /** The request could not be made or must wait. The token is still held. */
  | { kind: 'failed'; failure: AccountFailure }

export function EmailVerification({
  token,
  onSpent,
}: {
  /** The token from the link, or null once the API has answered for it. */
  token: string | null
  /** Called when the token is of no further use, so the screen drops it. */
  onSpent: () => void
}) {
  const { signedIn } = useSession()
  const [state, setState] = useState<VerificationState>({ kind: 'checking' })
  // A link is good once. This keeps one token from being posted twice, which
  // would turn a confirmation into "that link no longer works".
  const posted = useRef<string | null>(null)

  const verify = useCallback(
    async (linkToken: string): Promise<void> => {
      setState({ kind: 'checking' })
      try {
        await verifyEmail(linkToken)
        onSpent()
        setState({ kind: 'confirmed' })
      } catch (cause) {
        const failure = describeAccountFailure(cause, VERIFICATION_LINK_INVALID)
        // A token the API refuses outright is as dead as one it does not know.
        if (failure.kind === 'linkInvalid' || failure.kind === 'refused') {
          onSpent()
          setState({ kind: 'invalid' })
        } else {
          setState({ kind: 'failed', failure })
        }
      }
    },
    [onSpent],
  )

  useEffect(() => {
    if (token === null || posted.current === token) return
    posted.current = token
    void verify(token)
  }, [token, verify])

  if (state.kind === 'checking') {
    return <LoadingState label="Confirming your email address" shape="rows" count={1} />
  }

  if (state.kind === 'failed') {
    return (
      <AccountFailureNotice
        failure={state.failure}
        refusedTitle={VERIFICATION_INVALID_HEADING}
        faultHeading="We could not confirm your email address"
        onRetry={() => {
          if (token !== null) void verify(token)
        }}
      />
    )
  }

  if (state.kind === 'confirmed') {
    return (
      <Card>
        <StateHeading>{VERIFICATION_CONFIRMED_HEADING}</StateHeading>
        <p className="mt-sm text-sm text-slate-soft">
          Thank you. You can now confirm a hire online, and booking confirmations will reach you.
        </p>
        <Link to={signedIn ? ACCOUNT_PATH : SIGN_IN_PATH} className="btn-primary mt-lg px-lg">
          {signedIn ? 'Go to my account' : 'Sign in'}
        </Link>
      </Card>
    )
  }

  return (
    <Card>
      <StateHeading>{VERIFICATION_INVALID_HEADING}</StateHeading>
      <p className="mt-sm text-sm text-slate-soft">
        It may have been used already, or it is more than {VERIFICATION_LINK_HOURS} hours old.
        Nothing has been changed.
      </p>
      <p className="mt-sm text-sm text-slate-soft">
        {signedIn
          ? 'Open your account and choose Send the link again to get a new one.'
          : 'To get a new one, sign in and choose Send the link again on your account screen.'}
      </p>
      <Link
        to={signedIn ? ACCOUNT_PATH : signInAddress(ACCOUNT_PATH)}
        className="btn-primary mt-lg px-lg"
      >
        {signedIn ? 'Go to my account' : 'Sign in to send a new link'}
      </Link>
    </Card>
  )
}
