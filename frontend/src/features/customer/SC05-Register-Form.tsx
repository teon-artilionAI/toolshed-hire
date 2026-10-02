/**
 * The registration form of SC-05.
 *
 * Validation runs when a field is left and again on submit. Errors sit beside
 * the field they belong to, and the summary at the top jumps to the first
 * one, which is the quickest route through a long form on a phone. The rules
 * are in register-form.ts and the three cards are in register-cards.tsx.
 *
 * The form is sent once for each press of the button, and the button is
 * disabled while the request is in flight. A 422 puts each of the server's
 * sentences under the field it names, and it stays there until that field is
 * changed. A 429 says how long to wait. Anything else is the shared error
 * state with a way to try again.
 *
 * The branches in the menu are the ones the API lists. Until the person
 * chooses one, the first of them stands in.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { registerCustomer } from '../../shared/api/account'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { EmailDelivery } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { SIGN_IN_PATH } from '../../shared/navigation'
import { Notice } from '../../shared/ui'
import { describeAccountFailure } from './account-failure'
import type { AccountFailure } from './account-failure'
import { AccountFailureNotice } from './account-failure-notice'
import { ErrorSummary } from './customer-fields'
import { IdentificationCard, PasswordAndPrivacyCard, YourDetailsCard } from './register-cards'
import type { FieldWiring } from './register-cards'
import {
  EMPTY_REGISTRATION,
  REGISTRATION_FIELD_ORDER,
  toRegisterRequest,
  validateRegistration,
  withText,
} from './register-form'
import type { RegistrationField, RegistrationForm, TextFieldName } from './register-form'

const NO_SERVER_ERRORS: FieldErrors = {}

export function RegisterForm({
  onSent,
}: {
  /** Called with the address that was typed and what the API said about email. */
  onSent: (email: string, delivery: EmailDelivery) => void
}) {
  const [form, setForm] = useState<RegistrationForm>(EMPTY_REGISTRATION)
  const [touched, setTouched] = useState<Partial<Record<RegistrationField, boolean>>>({})
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<AccountFailure | null>(null)
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_SERVER_ERRORS)
  // State updates land after the event that caused them. This flag is set in
  // the same tick as the request, so a second press can never start another.
  const inFlight = useRef(false)

  const branches = useQuery(catalogueQueries.branches())
  const branchList = branches.data?.items ?? []
  const branchCodes = branchList.map((branch) => branch.code)
  // Until the person chooses, the first branch the API lists stands in.
  const answers: RegistrationForm = {
    ...form,
    homeBranchCode: form.homeBranchCode || (branchCodes[0] ?? ''),
  }

  const clientErrors = validateRegistration(answers, branchCodes)
  const hasClientErrors = REGISTRATION_FIELD_ORDER.some((field) => clientErrors[field])
  const problems = REGISTRATION_FIELD_ORDER.flatMap((field) => {
    const message = serverErrors[field] || clientErrors[field]
    return message ? [{ id: field, message }] : []
  })

  function errorFor(field: RegistrationField): string | undefined {
    if (serverErrors[field]) return serverErrors[field]
    return submitted || touched[field] ? clientErrors[field] : undefined
  }

  /** A field has changed, so what the server said about its old value goes. */
  function forgetServerError(field: RegistrationField) {
    if (!serverErrors[field]) return
    setServerErrors((current) =>
      Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)),
    )
  }

  /** What every text box and menu of the form is wired with. */
  function control(field: TextFieldName): FieldWiring {
    return {
      id: field,
      value: answers[field],
      onChange: (value) => {
        setForm((current) => withText(current, field, value))
        forgetServerError(field)
      },
      onBlur: () => setTouched((current) => ({ ...current, [field]: true })),
      error: errorFor(field),
    }
  }

  async function send(): Promise<void> {
    setSubmitted(true)
    if (hasClientErrors || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    setServerErrors(NO_SERVER_ERRORS)
    try {
      const delivery = await registerCustomer(toRegisterRequest(answers))
      onSent(answers.email.trim(), delivery)
    } catch (cause) {
      const described = describeAccountFailure(cause)
      setFailure(described)
      if (described.kind === 'refused') setServerErrors(described.fields)
      setBusy(false)
    } finally {
      inFlight.current = false
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  return (
    <>
      {submitted && problems.length > 0 && (
        <div className="mb-lg">
          <Notice
            tone="error"
            title={`We cannot open the account yet. ${problems.length} ${
              problems.length === 1 ? 'answer needs' : 'answers need'
            } fixing.`}
          >
            <ErrorSummary problems={problems} />
          </Notice>
        </div>
      )}
      {failure && (
        <div className="mb-lg">
          <AccountFailureNotice
            failure={failure}
            refusedTitle="We could not open the account with those details"
            faultHeading="We could not send your details"
            fieldsAreShown={problems.length > 0}
            otherMessages={otherFieldMessages(serverErrors, REGISTRATION_FIELD_ORDER)}
            onRetry={() => void send()}
          />
        </div>
      )}

      <form noValidate onSubmit={handleSubmit}>
        <YourDetailsCard control={control} />
        <div className="mt-lg">
          <IdentificationCard
            control={control}
            choices={{
              phase: queryPhase(branches),
              branches: branchList,
              error: branches.error,
              onRetry: () => void branches.refetch(),
            }}
          />
        </div>
        <div className="mt-lg">
          <PasswordAndPrivacyCard
            control={control}
            accepted={form.acceptsPrivacyNotice}
            onAccept={(accepted) => {
              setForm((current) => ({ ...current, acceptsPrivacyNotice: accepted }))
              forgetServerError('acceptsPrivacyNotice')
            }}
            acceptError={errorFor('acceptsPrivacyNotice')}
          />
        </div>

        <div className="mt-lg flex flex-wrap items-center gap-sm">
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {busy ? 'Creating your account' : 'Create my account'}
          </button>
          <Link to={SIGN_IN_PATH} className="btn-ghost px-md">
            I already have an account
          </Link>
        </div>
        <p className="sr-only" role="status">
          {busy ? 'Sending your details, please wait' : ''}
        </p>
      </form>
    </>
  )
}
