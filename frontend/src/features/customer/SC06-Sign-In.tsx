/**
 * SC-06 Sign In and Password Reset.
 *
 * One screen, three states: signing in, asking for a reset link, and
 * choosing the new password once the link has been followed. They live
 * together because they are one job from the customer's side, which is
 * getting back into the account. A reset link opens this screen with
 * ?reset=1, so the third state is reachable without inventing a route.
 *
 * Signing in genuinely changes the session, so the rest of the prototype
 * behaves as that role afterwards.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { users } from '../../shared/fixtures'
import { ROLE_HOME, ROLE_LABEL } from '../../shared/navigation'
import { useSession } from '../../shared/session'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { PasswordField, TextField, isEmailWellFormed } from './customer-fields'
import {
  ChooseNewPasswordPanel,
  ForgotPasswordPanel,
} from './password-reset-panels'

type Mode = 'signin' | 'forgot' | 'reset'

const TITLE: Record<Mode, string> = {
  signin: 'Sign in to Toolshed Hire',
  forgot: 'Reset your password',
  reset: 'Choose a new password',
}

const SUBTITLE: Record<Mode, string> = {
  signin: 'Your bookings, deposits and hire history are behind this door.',
  forgot: 'We will email a link that lets you set a new password.',
  reset: 'Pick something you have not used on this account before.',
}

/** Customers land on their hires rather than the catalogue, because the
 *  reason to sign in is almost always to check a booking. */
const CUSTOMER_LANDING = '/reservations'

function SignInPanel({ onForgot }: { onForgot: () => void }) {
  const { signInAs } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const emailError = !email.trim()
    ? 'Enter the email address on your account.'
    : !isEmailWellFormed(email)
      ? 'That email address is missing an @ or a domain. Check it and try again.'
      : undefined
  const passwordError = !password ? 'Enter your password.' : undefined

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    setFormError(null)
    if (emailError || passwordError) return

    const account = users.find(
      (user) => user.email.toLowerCase() === email.trim().toLowerCase(),
    )
    if (!account) {
      setFormError(
        'Those details do not match an account. Check the email address, or create an account.',
      )
      return
    }
    if (!account.active) {
      setFormError(
        `The account for ${account.email} has been deactivated. Ask a branch manager to switch it back on.`,
      )
      return
    }

    signInAs(account.role)
    navigate(
      account.role === 'customer' ? CUSTOMER_LANDING : ROLE_HOME[account.role],
    )
  }

  return (
    <Card title="Sign in">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        {formError && (
          <Notice tone="error" title="We could not sign you in">
            <p>{formError}</p>
          </Notice>
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
          <button type="submit" className="btn-primary px-lg">
            Sign in
          </button>
          <button type="button" className="btn-ghost px-md" onClick={onForgot}>
            Forgotten your password?
          </button>
        </div>
      </form>
    </Card>
  )
}

/** Marking this prototype means signing in as three different people. The
 *  addresses are on screen so nobody has to go digging for them, and the
 *  panel is labelled as a demonstration aid so it is never mistaken for
 *  part of the product. */
function PrototypeNote() {
  return (
    <div className="mt-lg rounded-lg border-2 border-dashed border-slate-faint bg-muted p-md">
      <p className="flex items-center gap-sm font-mono text-xs uppercase tracking-wide text-slate-soft">
        <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
        Prototype note
      </p>
      <p className="mt-sm text-sm text-slate-soft">
        There is no back end yet, so any password is accepted. These are the
        accounts that exist.
      </p>
      <ul className="mt-sm flex flex-col gap-xs text-sm text-ink">
        {users.map((user) => (
          <li key={user.id} className="flex flex-wrap items-baseline gap-x-sm">
            <span className="font-mono text-xs">{user.email}</span>
            <span className="text-xs text-slate-soft">
              {ROLE_LABEL[user.role]}
              {user.active ? '' : ', deactivated'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function SignIn() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(params.get('reset') ? 'reset' : 'signin')
  const [resetEmail, setResetEmail] = useState<string | null>(null)

  return (
    <>
      <PageHeader screenId="SC-06" title={TITLE[mode]} subtitle={SUBTITLE[mode]} />

      <div className="mx-auto w-full max-w-lg">
        {mode === 'signin' && <SignInPanel onForgot={() => setMode('forgot')} />}

        {mode === 'forgot' && (
          <ForgotPasswordPanel
            onBackToSignIn={() => setMode('signin')}
            onHaveLink={(email) => {
              setResetEmail(email)
              setMode('reset')
            }}
          />
        )}

        {mode === 'reset' && (
          <ChooseNewPasswordPanel
            email={resetEmail}
            onDone={() => setMode('signin')}
          />
        )}

        {mode === 'signin' && (
          <p className="mt-lg text-center text-sm text-slate-soft">
            No account yet?{' '}
            <Link
              to="/register"
              className="cursor-pointer font-medium text-ink underline transition-colors duration-200 hover:text-slate"
            >
              Create one in about two minutes
            </Link>
            .
          </p>
        )}

        <PrototypeNote />
      </div>
    </>
  )
}
