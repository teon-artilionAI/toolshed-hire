/**
 * SC-06 Sign In and Password Reset.
 *
 * Signing in sends the email address and password that were typed to the API.
 * The answer is a session, kept by shared/session-store.ts. This screen keeps
 * neither the password nor the token.
 *
 * A person arrives here in one of three ways, and the screen says which. They
 * chose to sign in. They opened a screen that needs an account, and the guard
 * sent them here with that address in `?next=`. Or their session ended while
 * they were working. In the last two cases they are taken back to where they
 * were once they are signed in. Otherwise they land on the home of their role.
 *
 * Somebody who is already signed in has no use for this screen, so it sends
 * them on at once. That same rule is what moves a person on after a
 * successful sign in, so there is one path and not two.
 *
 * Password reset is a later change. Its state is still here, reachable from
 * the form and from `?reset=1`, and it says plainly that it is not available.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { ErrorState } from '../../shared/async-states'
import { NEXT_PARAMETER, landingFor } from '../../shared/screen-access'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { PasswordField, TextField, isEmailWellFormed } from './customer-fields'
import { PasswordResetUnavailable } from './password-reset-panels'
import { describeSignInFailure } from './sign-in-failure'
import type { SignInFailure } from './sign-in-failure'

type Mode = 'signin' | 'reset'

/** The query parameter a reset link opens this screen with. */
const RESET_PARAMETER = 'reset'

const TITLE: Record<Mode, string> = {
  signin: 'Sign in to Toolshed Hire',
  reset: 'Reset your password',
}

const SUBTITLE: Record<Mode, string> = {
  signin: 'Your bookings, deposits and hire history are behind this door.',
  reset: 'Resetting a password from here is not available yet.',
}

function SignInPanel({ onForgot }: { onForgot: () => void }) {
  const { signIn } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<SignInFailure | null>(null)
  // State updates land after the event that caused them. This flag is set in
  // the same tick as the request, so a second press can never start another.
  const inFlight = useRef(false)

  const emailError = !email.trim()
    ? 'Enter the email address on your account.'
    : !isEmailWellFormed(email)
      ? 'That email address is missing an @ or a domain. Check it and try again.'
      : undefined
  const passwordError = !password ? 'Enter your password.' : undefined

  async function attempt(): Promise<void> {
    setSubmitted(true)
    if (emailError || passwordError || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    try {
      // On success the session changes and the screen above sends the person
      // on, so there is nothing more to do here.
      await signIn(email.trim(), password)
    } catch (cause) {
      setFailure(describeSignInFailure(cause))
      setBusy(false)
    } finally {
      inFlight.current = false
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void attempt()
  }

  return (
    <Card title="Sign in">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        {failure?.kind === 'refused' && (
          <Notice tone="error" title="We could not sign you in">
            <p>{failure.message}</p>
          </Notice>
        )}
        {failure?.kind === 'wait' && (
          <Notice tone="error" title="Too many attempts">
            <p>{failure.message}</p>
          </Notice>
        )}
        {failure?.kind === 'fault' && (
          <ErrorState
            heading="We could not sign you in"
            error={failure.error}
            onRetry={() => void attempt()}
          />
        )}
        <TextField
          id="signin-email"
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="username"
          value={email}
          onChange={setEmail}
          onBlur={() => setSubmitted(true)}
          error={submitted ? emailError : undefined}
          required
        />
        <PasswordField
          id="signin-password"
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          onBlur={() => setSubmitted(true)}
          error={submitted ? passwordError : undefined}
        />
        <div className="flex flex-wrap items-center gap-sm">
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {busy ? 'Signing in' : 'Sign in'}
          </button>
          <button type="button" className="btn-ghost px-md" onClick={onForgot}>
            Forgotten your password?
          </button>
        </div>
        <p className="sr-only" role="status">
          {busy ? 'Signing in, please wait' : ''}
        </p>
      </form>
    </Card>
  )
}

/** Why the person is on this screen, when it was not their own idea. */
function ArrivalNotice({ expired, hasNext }: { expired: boolean; hasNext: boolean }) {
  if (expired) {
    return (
      <div className="mb-lg">
        <Notice tone="warn" title="Your session has ended">
          <p>
            {hasNext
              ? 'Sign in again and we will take you back to where you were.'
              : 'Sign in again to carry on.'}
          </p>
        </Notice>
      </div>
    )
  }
  if (!hasNext) return null
  return (
    <div className="mb-lg">
      <Notice tone="info" title="Sign in to carry on">
        <p>That screen needs an account. Once you are signed in we will take you straight to it.</p>
      </Notice>
    </div>
  )
}

export default function SignIn() {
  const { user, endedBecause } = useSession()
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(params.get(RESET_PARAMETER) ? 'reset' : 'signin')
  const next = params.get(NEXT_PARAMETER)

  if (user) return <Navigate to={landingFor(user.role, next)} replace />

  return (
    <>
      <PageHeader screenId="SC-06" title={TITLE[mode]} subtitle={SUBTITLE[mode]} />

      <div className="mx-auto w-full max-w-lg">
        {mode === 'signin' && (
          <>
            <ArrivalNotice expired={endedBecause === 'expired'} hasNext={next !== null} />
            <SignInPanel onForgot={() => setMode('reset')} />
            <p className="mt-lg text-center text-sm text-slate-soft">
              No account yet?{' '}
              <Link
                to="/register"
                className="cursor-pointer font-medium text-ink underline transition-colors duration-200 hover:text-slate"
              >
                Go to the registration screen
              </Link>
              .
            </p>
          </>
        )}

        {mode === 'reset' && <PasswordResetUnavailable onBackToSignIn={() => setMode('signin')} />}
      </div>
    </>
  )
}
