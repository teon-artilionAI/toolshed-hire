/**
 * SC-05 Register.
 *
 * A hire account needs more than an email address, because the counter has
 * to check identification against the booking before releasing a machine
 * worth thirty thousand rand. So the form asks for it up front rather than
 * springing it on someone standing at the counter with a bakkie outside.
 *
 * Validation runs when a field is left and again on submit. Errors sit
 * beside the field they belong to, and the summary at the top jumps to the
 * first one, which is the quickest route through a long form on a phone.
 * The rules themselves live in register-form.ts.
 */

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import { Card, Notice, PageHeader } from '../../shared/ui'
import type { BranchCode } from '../../shared/types'
import {
  CheckboxField,
  ErrorSummary,
  MIN_PASSWORD_LENGTH,
  PasswordField,
  SelectField,
  TextField,
} from './customer-fields'
import { ID_DOC_LABEL } from './customer-labels'
import {
  EMPTY_REGISTRATION,
  REGISTRATION_FIELD_ORDER,
  validateRegistration,
} from './register-form'
import type {
  IdDocType,
  RegistrationErrors,
  RegistrationField,
  RegistrationForm,
} from './register-form'
import { RegisterSuccessCard } from './register-success-card'

/** How long the fake account creation takes, so the loading state is real
 *  enough to see rather than a flash. */
const SAVE_DELAY_MS = 700

export default function Register() {
  const [form, setForm] = useState<RegistrationForm>(EMPTY_REGISTRATION)
  const [touched, setTouched] = useState<
    Partial<Record<RegistrationField, boolean>>
  >({})
  const [submitted, setSubmitted] = useState(false)
  const [status, setStatus] = useState<'idle' | 'saving' | 'done'>('idle')

  const errors = validateRegistration(form)
  const shownErrors: RegistrationErrors = {}
  for (const field of REGISTRATION_FIELD_ORDER) {
    if ((submitted || touched[field]) && errors[field]) {
      shownErrors[field] = errors[field]
    }
  }
  const problems = REGISTRATION_FIELD_ORDER.filter(
    (field) => errors[field],
  ).map((field) => ({ id: field, message: errors[field] as string }))

  useEffect(() => {
    if (status !== 'saving') return
    const timer = window.setTimeout(() => setStatus('done'), SAVE_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [status])

  function markTouched(field: RegistrationField) {
    setTouched((current) => ({ ...current, [field]: true }))
  }

  function update<K extends RegistrationField>(
    field: K,
    value: RegistrationForm[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    if (problems.length > 0) return
    setStatus('saving')
  }

  if (status === 'done') {
    return (
      <>
        <PageHeader
          screenId="SC-05"
          title="Your account is ready"
          subtitle={`We have sent a confirmation to ${form.email.trim()}.`}
        />
        <RegisterSuccessCard form={form} />
      </>
    )
  }

  const saving = status === 'saving'

  return (
    <>
      <PageHeader
        screenId="SC-05"
        title="Create your hire account"
        subtitle="It takes about two minutes. We ask for identification now so that collection at the counter is quick."
      />

      <div className="mx-auto w-full max-w-2xl">
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

        <form noValidate onSubmit={handleSubmit}>
          <Card title="Your details">
            <div className="flex flex-col gap-md">
              <TextField
                id="fullName"
                label="Full name"
                autoComplete="name"
                value={form.fullName}
                onChange={(v) => update('fullName', v)}
                onBlur={() => markTouched('fullName')}
                help="As it appears on your identity document."
                error={shownErrors.fullName}
                required
              />
              <TextField
                id="email"
                label="Email address"
                type="email"
                inputMode="email"
                autoComplete="email"
                value={form.email}
                onChange={(v) => update('email', v)}
                onBlur={() => markTouched('email')}
                help="Booking confirmations and return reminders go here."
                error={shownErrors.email}
                required
              />
              <TextField
                id="mobile"
                label="Mobile number"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="082 441 7719"
                value={form.mobile}
                onChange={(v) => update('mobile', v)}
                onBlur={() => markTouched('mobile')}
                error={shownErrors.mobile}
                required
              />
            </div>
          </Card>

          <div className="mt-lg">
            <Card title="Identification and billing">
              <div className="flex flex-col gap-md">
                <SelectField
                  id="idDocType"
                  label="Identity document"
                  value={form.idDocType}
                  onChange={(v) => update('idDocType', v as IdDocType)}
                  options={(Object.keys(ID_DOC_LABEL) as IdDocType[]).map(
                    (key) => ({ value: key, label: ID_DOC_LABEL[key] }),
                  )}
                />
                <TextField
                  id="idDocNumber"
                  label={`${ID_DOC_LABEL[form.idDocType]} number`}
                  inputMode={form.idDocType === 'SA_ID' ? 'numeric' : 'text'}
                  value={form.idDocNumber}
                  onChange={(v) => update('idDocNumber', v)}
                  onBlur={() => markTouched('idDocNumber')}
                  help="Only the last few digits are shown back to you once the account is open."
                  error={shownErrors.idDocNumber}
                  required
                />
                <div className="grid gap-md sm:grid-cols-2">
                  <TextField
                    id="billingSuburb"
                    label="Billing suburb"
                    autoComplete="address-level2"
                    value={form.billingSuburb}
                    onChange={(v) => update('billingSuburb', v)}
                    onBlur={() => markTouched('billingSuburb')}
                    error={shownErrors.billingSuburb}
                    required
                  />
                  <TextField
                    id="billingCity"
                    label="Billing city"
                    autoComplete="address-level1"
                    value={form.billingCity}
                    onChange={(v) => update('billingCity', v)}
                    onBlur={() => markTouched('billingCity')}
                    error={shownErrors.billingCity}
                    required
                  />
                </div>
                <SelectField
                  id="homeBranch"
                  label="Usual collection branch"
                  value={form.homeBranch}
                  onChange={(v) => update('homeBranch', v as BranchCode)}
                  help="You can choose a different branch on any booking."
                  options={branches.map((branch) => ({
                    value: branch.code,
                    label: `${branch.name}, ${branch.suburb}`,
                  }))}
                />
              </div>
            </Card>
          </div>

          <div className="mt-lg">
            <Card title="Set a password">
              <div className="flex flex-col gap-md">
                <PasswordField
                  id="password"
                  label="Password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(v) => update('password', v)}
                  onBlur={() => markTouched('password')}
                  help={`At least ${MIN_PASSWORD_LENGTH} characters, including a number.`}
                  error={shownErrors.password}
                />
                <PasswordField
                  id="confirmPassword"
                  label="Confirm password"
                  autoComplete="new-password"
                  value={form.confirmPassword}
                  onChange={(v) => update('confirmPassword', v)}
                  onBlur={() => markTouched('confirmPassword')}
                  error={shownErrors.confirmPassword}
                />
                <CheckboxField
                  id="acceptsTerms"
                  checked={form.acceptsTerms}
                  onChange={(v) => update('acceptsTerms', v)}
                  error={shownErrors.acceptsTerms}
                >
                  I accept the hire terms. I understand a refundable deposit is
                  taken at collection and that late returns are charged per day.
                </CheckboxField>
              </div>
            </Card>
          </div>

          <div className="mt-lg flex flex-wrap items-center gap-sm">
            <button type="submit" className="btn-primary px-lg" disabled={saving}>
              {saving && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {saving ? 'Creating your account' : 'Create my account'}
            </button>
            <Link to="/signin" className="btn-ghost px-md">
              I already have an account
            </Link>
          </div>
          <p className="sr-only" role="status" aria-live="polite">
            {saving ? 'Creating your account, please wait' : ''}
          </p>
        </form>
      </div>
    </>
  )
}
