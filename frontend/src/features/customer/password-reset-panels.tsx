/**
 * The two password reset states of SC-06.
 *
 * Requesting a link and choosing a new password are separate moments in the
 * same screen, so they are separate components rather than one panel with a
 * pile of flags. Neither confirms whether an email address is registered,
 * because that would hand an attacker a list of customers.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { MailCheck } from 'lucide-react'
import { Card, Notice } from '../../shared/ui'
import {
  MIN_PASSWORD_LENGTH,
  PasswordField,
  TextField,
  isEmailWellFormed,
  passwordProblem,
} from './customer-fields'

/** How long a reset link is good for. Stated on screen so nobody is
 *  surprised when an old link stops working. */
const RESET_LINK_MINUTES = 30

export function ForgotPasswordPanel({
  onBackToSignIn,
  onHaveLink,
}: {
  onBackToSignIn: () => void
  onHaveLink: (email: string) => void
}) {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const error = !email.trim()
    ? 'Enter the email address you signed up with.'
    : !isEmailWellFormed(email)
      ? 'That email address is missing an @ or a domain. Check it and try again.'
      : undefined

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    if (error) return
    setSentTo(email.trim())
  }

  if (sentTo) {
    return (
      <Card title="Check your email">
        <div className="flex items-start gap-md">
          <MailCheck
            className="mt-xs h-6 w-6 shrink-0 text-status-available"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm text-ink">
              If we have an account for {sentTo}, a link to set a new password
              is on its way. It stops working after {RESET_LINK_MINUTES}{' '}
              minutes.
            </p>
            <p className="mt-sm text-sm text-slate-soft">
              Nothing arrived? Look in your junk folder, then try again. We do
              not say whether an address is registered, so no email is not
              proof of anything.
            </p>
            <div className="mt-lg flex flex-wrap gap-sm">
              <button
                type="button"
                className="btn-primary px-md"
                onClick={() => onHaveLink(sentTo)}
              >
                I have the link, set my password
              </button>
              <button
                type="button"
                className="btn-secondary px-md"
                onClick={onBackToSignIn}
              >
                Back to sign in
              </button>
            </div>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card title="Reset your password">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        <p className="text-sm text-slate-soft">
          Tell us the address on your account and we will send a link to set a
          new password.
        </p>
        <TextField
          id="reset-email"
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          onBlur={() => setSubmitted(true)}
          error={submitted ? error : undefined}
          required
        />
        <div className="flex flex-wrap items-center gap-sm">
          <button type="submit" className="btn-primary px-lg">
            Send the reset link
          </button>
          <button
            type="button"
            className="btn-ghost px-md"
            onClick={onBackToSignIn}
          >
            Back to sign in
          </button>
        </div>
      </form>
    </Card>
  )
}

export function ChooseNewPasswordPanel({
  email,
  onDone,
}: {
  /** The address the link was sent to, if we came from the request step. */
  email: string | null
  onDone: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [changed, setChanged] = useState(false)

  const passwordError = passwordProblem(password)
  const confirmError = !confirmPassword
    ? 'Type the new password a second time so we know it was not a slip.'
    : confirmPassword !== password
      ? 'The two passwords are not the same. Retype them both.'
      : undefined

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    if (passwordError || confirmError) return
    setChanged(true)
  }

  if (changed) {
    return (
      <Card title="Password changed">
        <Notice tone="success" title="Your password has been changed">
          <p>
            Any other device signed in to this account has been signed out. Use
            the new password from now on.
          </p>
        </Notice>
        <button type="button" className="btn-primary mt-lg px-lg" onClick={onDone}>
          Sign in with the new password
        </button>
      </Card>
    )
  }

  return (
    <Card title="Choose a new password">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        <p className="text-sm text-slate-soft">
          {email
            ? `Setting a new password for ${email}.`
            : 'Setting a new password from your reset link.'}
        </p>
        <PasswordField
          id="new-password"
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          onBlur={() => setSubmitted(true)}
          help={`At least ${MIN_PASSWORD_LENGTH} characters, including a number.`}
          error={submitted ? passwordError : undefined}
        />
        <PasswordField
          id="confirm-new-password"
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          onBlur={() => setSubmitted(true)}
          error={submitted ? confirmError : undefined}
        />
        <div>
          <button type="submit" className="btn-primary px-lg">
            Save the new password
          </button>
        </div>
      </form>
    </Card>
  )
}
