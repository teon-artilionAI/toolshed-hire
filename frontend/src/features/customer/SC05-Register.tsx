/**
 * SC-05 Register.
 *
 * A hire account needs more than an email address, because the counter has
 * to check identification against the booking before releasing a machine
 * worth thirty thousand rand. So the form asks for it up front rather than
 * springing it on someone standing at the counter with a bakkie outside.
 *
 * The screen has three states. The form, which is SC05-Register-Form.tsx.
 * What it says once the form has been sent. And where the link in the
 * verification email lands, which is SC05-Email-Verification.tsx.
 *
 * The API answers a registration the same way whether or not the address
 * already has an account, and so does this screen. It says that a link was
 * sent if the address is new, and it never says which it was. The browser
 * holds no list of accounts to look in.
 *
 * When the API says the email cannot be delivered, the screen says that too,
 * with what the person can still do, so nobody waits for a link that is not
 * coming.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { VERIFICATION_LINK_HOURS } from '../../shared/api/account'
import type { EmailDelivery } from '../../shared/api/contract'
import { SIGN_IN_PATH } from '../../shared/navigation'
import { Card, PageHeader } from '../../shared/ui'
import { DemonstrationEmailNote, WITHOUT_THE_LINK } from './email-delivery-note'
import { EmailVerification } from './SC05-Email-Verification'
import { RegisterForm } from './SC05-Register-Form'
import { StateHeading } from './state-heading'
import { VERIFY_LINK_NAME, useLinkToken } from './use-link-token'

export const CHECK_YOUR_EMAIL_HEADING = 'Check your email'

/** The one thing the screen says about the address, whoever it belongs to. */
export const REGISTRATION_SENT_MESSAGE = 'If that address is new, we have sent it a link.'

interface RegistrationSent {
  email: string
  delivery: EmailDelivery
}

function CheckYourEmail({ email, delivery }: RegistrationSent) {
  return (
    <Card>
      <StateHeading>{CHECK_YOUR_EMAIL_HEADING}</StateHeading>
      <p className="mt-sm text-sm text-ink">
        {REGISTRATION_SENT_MESSAGE} The address you gave is{' '}
        <span className="break-all font-medium">{email}</span>.
        {delivery.emailDeliverable &&
          ` Open the link within ${VERIFICATION_LINK_HOURS} hours to confirm it.`}
      </p>
      <p className="mt-sm text-sm text-slate-soft">
        If that address already has an account, nothing has changed. Sign in with it, or reset the
        password from the sign in screen.
      </p>
      {!delivery.emailDeliverable && (
        <div className="mt-md">
          <DemonstrationEmailNote>{WITHOUT_THE_LINK}</DemonstrationEmailNote>
        </div>
      )}
      <Link to={SIGN_IN_PATH} className="btn-primary mt-lg px-lg">
        Go to sign in
      </Link>
    </Card>
  )
}

export default function Register() {
  const link = useLinkToken(VERIFY_LINK_NAME)
  const [verifying, setVerifying] = useState(link.token !== null)
  const [sent, setSent] = useState<RegistrationSent | null>(null)

  // A verification link opened while the form was already on the page.
  if (link.token !== null && !verifying) setVerifying(true)

  if (verifying) {
    return (
      <>
        <PageHeader
          screenId="SC-05"
          title="Confirm your email address"
          subtitle="The link in your email brought you here. It works once."
        />
        <div className="mx-auto w-full max-w-2xl">
          <EmailVerification token={link.token} onSpent={link.forget} />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader
        screenId="SC-05"
        title="Create your hire account"
        subtitle="It takes about two minutes. We ask for identification now so that collection at the counter is quick."
      />
      <div className="mx-auto w-full max-w-2xl">
        {sent ? (
          <CheckYourEmail email={sent.email} delivery={sent.delivery} />
        ) : (
          <RegisterForm onSent={(email, delivery) => setSent({ email, delivery })} />
        )}
      </div>
    </>
  )
}
