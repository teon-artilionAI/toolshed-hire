/**
 * The two password reset states of SC-06.
 *
 * Asking for a link takes an email address and sends it. What it says
 * afterwards is one message, the same whether or not the address has an
 * account, because a different one would tell a stranger which addresses do.
 *
 * Choosing a new password is where the link in the email lands. It takes the
 * password twice, sends it once with the token, and then says the password
 * has changed and that every device has been signed out. A link that is
 * unknown, already used or more than an hour old gets one answer, and the way
 * forward is to ask for a new one.
 *
 * The token is dropped as soon as the API has answered for it.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import {
  MIN_PASSWORD_LENGTH,
  RESET_LINK_INVALID,
  RESET_LINK_MINUTES,
  completePasswordReset,
  requestPasswordReset,
} from '../../shared/api/account'
import type { EmailDelivery } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { Card } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { describeAccountFailure } from './account-failure'
import type { AccountFailure } from './account-failure'
import { AccountFailureNotice } from './account-failure-notice'
import { PasswordField, TextField } from './customer-fields'
import { confirmationProblem, isEmailWellFormed, passwordProblem } from './customer-rules'
import { DemonstrationEmailNote } from './email-delivery-note'
import { StateHeading } from './state-heading'

/** The one thing the screen says after a reset is asked for, whoever asked. */
export const RESET_SENT_MESSAGE = `If that address has an account, we have sent it a link to choose a new password. The link works once, for ${RESET_LINK_MINUTES} minutes.`

/** The same, where this environment cannot deliver mail to the address given. */
export const RESET_HELD_MESSAGE =
  'If that address has an account, this demonstration cannot email it the link to choose a new password.'

export const RESET_DONE_HEADING = 'Your password has changed'
export const RESET_LINK_INVALID_HEADING = 'That reset link no longer works'

const NO_FIELDS: FieldErrors = {}
const EMAIL_FIELD = 'email'
const NEW_PASSWORD_FIELD = 'newPassword'

function BusyIcon({ busy }: { busy: boolean }) {
  return busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null
}

export function PasswordResetRequest({ onBackToSignIn }: { onBackToSignIn: () => void }) {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<AccountFailure | null>(null)
  const [sent, setSent] = useState<EmailDelivery | null>(null)
  const inFlight = useRef(false)

  const emailError = !email.trim()
    ? 'Enter the email address on your account.'
    : !isEmailWellFormed(email)
      ? 'That email address is missing an @ or a domain. Check it and try again.'
      : undefined
  const refusedFields: FieldErrors = failure?.kind === 'refused' ? failure.fields : NO_FIELDS
  const shownError = refusedFields[EMAIL_FIELD] ?? (submitted ? emailError : undefined)

  async function send(): Promise<void> {
    setSubmitted(true)
    if (emailError || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    try {
      setSent(await requestPasswordReset(email.trim()))
    } catch (cause) {
      setFailure(describeAccountFailure(cause))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  if (sent) {
    return (
      <Card>
        <StateHeading>Check your email</StateHeading>
        <p className="mt-sm text-sm text-ink">
          {sent.emailDeliverable ? RESET_SENT_MESSAGE : RESET_HELD_MESSAGE}
        </p>
        {!sent.emailDeliverable && (
          <div className="mt-md">
            <DemonstrationEmailNote>Your password has not changed.</DemonstrationEmailNote>
          </div>
        )}
        <button type="button" className="btn-primary mt-lg px-lg" onClick={onBackToSignIn}>
          Back to sign in
        </button>
      </Card>
    )
  }

  return (
    <Card title="Reset your password">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        {failure && (
          <AccountFailureNotice
            failure={failure}
            refusedTitle="We could not send a link to that address"
            faultHeading="We could not ask for a reset link"
            fieldsAreShown={Boolean(refusedFields[EMAIL_FIELD])}
            otherMessages={otherFieldMessages(refusedFields, [EMAIL_FIELD])}
            onRetry={() => void send()}
          />
        )}
        <TextField
          id="reset-email"
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="username"
          value={email}
          onChange={(value) => {
            setEmail(value)
            // The server's sentence was about the old address, so it goes with it.
            if (failure?.kind === 'refused') setFailure(null)
          }}
          help="We send a link to this address. The link opens a screen where you choose a new password."
          error={shownError}
          required
        />
        <div className="flex flex-wrap items-center gap-sm">
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            <BusyIcon busy={busy} />
            {busy ? 'Sending the link' : 'Send me a reset link'}
          </button>
          <button type="button" className="btn-ghost px-md" onClick={onBackToSignIn}>
            Back to sign in
          </button>
        </div>
        <p className="sr-only" role="status">
          {busy ? 'Asking for a reset link, please wait' : ''}
        </p>
      </form>
    </Card>
  )
}

type CompletionStage = 'form' | 'changed' | 'linkInvalid'

export function PasswordResetCompletion({
  token,
  onSpent,
  onSignIn,
  onAskAgain,
}: {
  /** The token from the link, or null once the API has answered for it. */
  token: string | null
  /** Called when the token is of no further use, so the screen drops it. */
  onSpent: () => void
  onSignIn: () => void
  onAskAgain: () => void
}) {
  const { signedIn, endSessionHere } = useSession()
  const [stage, setStage] = useState<CompletionStage>('form')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<AccountFailure | null>(null)
  const inFlight = useRef(false)

  const passwordError = passwordProblem(password)
  const confirmationError = confirmationProblem(password, confirmation)
  const refusedFields: FieldErrors = failure?.kind === 'refused' ? failure.fields : NO_FIELDS
  const shownPasswordError =
    refusedFields[NEW_PASSWORD_FIELD] ?? (submitted ? passwordError : undefined)

  async function send(): Promise<void> {
    setSubmitted(true)
    if (passwordError || confirmationError || token === null || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    try {
      await completePasswordReset(token, password)
      onSpent()
      // The server has ended every session of the account. This page was one
      // of them if somebody was signed in, so it is ended here as well.
      if (signedIn) await endSessionHere()
      setStage('changed')
    } catch (cause) {
      const described = describeAccountFailure(cause, RESET_LINK_INVALID)
      if (described.kind === 'linkInvalid') {
        onSpent()
        setStage('linkInvalid')
      } else {
        setFailure(described)
      }
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  if (stage === 'changed') {
    return (
      <Card>
        <StateHeading>{RESET_DONE_HEADING}</StateHeading>
        <p className="mt-sm text-sm text-ink">
          Every device that was signed in to your account has been signed out. Sign in with the
          new password to carry on.
        </p>
        <button type="button" className="btn-primary mt-lg px-lg" onClick={onSignIn}>
          Sign in
        </button>
      </Card>
    )
  }

  if (stage === 'linkInvalid') {
    return (
      <Card>
        <StateHeading>{RESET_LINK_INVALID_HEADING}</StateHeading>
        <p className="mt-sm text-sm text-ink">
          It may have been used already, or it is more than {RESET_LINK_MINUTES} minutes old. Your
          password has not changed.
        </p>
        <button type="button" className="btn-primary mt-lg px-lg" onClick={onAskAgain}>
          Ask for a new link
        </button>
      </Card>
    )
  }

  return (
    <Card title="Choose a new password">
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
        {failure && (
          <AccountFailureNotice
            failure={failure}
            refusedTitle="We could not change the password"
            faultHeading="We could not change the password"
            fieldsAreShown={Boolean(refusedFields[NEW_PASSWORD_FIELD])}
            otherMessages={otherFieldMessages(refusedFields, [NEW_PASSWORD_FIELD])}
            onRetry={() => void send()}
          />
        )}
        <PasswordField
          id="reset-new-password"
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(value) => {
            setPassword(value)
            if (failure?.kind === 'refused') setFailure(null)
          }}
          help={`At least ${MIN_PASSWORD_LENGTH} characters.`}
          error={shownPasswordError}
        />
        <PasswordField
          id="reset-confirm-password"
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmation}
          onChange={setConfirmation}
          error={submitted ? confirmationError : undefined}
        />
        <div className="flex flex-wrap items-center gap-sm">
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            <BusyIcon busy={busy} />
            {busy ? 'Changing your password' : 'Change my password'}
          </button>
          <button type="button" className="btn-ghost px-md" onClick={onSignIn}>
            Back to sign in
          </button>
        </div>
        <p className="sr-only" role="status">
          {busy ? 'Changing your password, please wait' : ''}
        </p>
      </form>
    </Card>
  )
}
