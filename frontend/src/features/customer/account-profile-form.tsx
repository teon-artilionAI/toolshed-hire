/**
 * The form a customer corrects their own details with, on SC-09.
 *
 * It holds the fields the API lets a customer change. Saving sends only the
 * ones that were changed, once for each press of the button, and what the
 * screen shows afterwards is the profile the server answered with.
 *
 * A 422 puts each of the server's sentences under the field it names. A
 * message about a field this form has no input for is listed above the form,
 * so it still reaches the person. A 429 says how long to wait, and anything
 * else is the shared error state with a way to try again.
 */

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Loader2 } from 'lucide-react'
import { updateMyProfile } from '../../shared/api/account'
import type { MyProfile } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { describeAccountFailure } from './account-failure'
import type { AccountFailure } from './account-failure'
import { AccountFailureNotice } from './account-failure-notice'
import { TextField } from './customer-fields'
import { PROFILE_FIELD_ORDER, changesIn, draftFrom, validateProfileChanges } from './profile-form'
import type { ProfileDraft, ProfileField } from './profile-form'

const NO_FIELDS: FieldErrors = {}

/** The id of the input for a field, kept apart from every other form's ids. */
function inputId(field: ProfileField): string {
  return `profile-${field}`
}

export function AccountProfileForm({
  profile,
  onSaved,
  onUnchanged,
  onDiscard,
}: {
  profile: MyProfile
  /** Called with the profile the server answered a save with. */
  onSaved: (updated: MyProfile) => void
  /** Called when the form was saved with nothing changed, so nothing was sent. */
  onUnchanged: () => void
  onDiscard: () => void
}) {
  const [draft, setDraft] = useState<ProfileDraft>(() => draftFrom(profile))
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<AccountFailure | null>(null)
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_FIELDS)
  const inFlight = useRef(false)

  const clientErrors = validateProfileChanges(profile, draft)
  const hasClientErrors = PROFILE_FIELD_ORDER.some((field) => clientErrors[field])
  const fieldsAreShown = PROFILE_FIELD_ORDER.some((field) => serverErrors[field])

  /** What every text box of the form is wired with. */
  function control(field: ProfileField) {
    return {
      id: inputId(field),
      value: draft[field],
      onChange: (value: string) => {
        setDraft((current) => ({ ...current, [field]: value }))
        // The server's sentence was about the old value, so it goes with it.
        if (serverErrors[field]) {
          setServerErrors((current) =>
            Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)),
          )
        }
      },
      error: serverErrors[field] || (submitted ? clientErrors[field] : undefined),
    }
  }

  async function save(): Promise<void> {
    setSubmitted(true)
    if (hasClientErrors || inFlight.current) return
    const changes = changesIn(profile, draft)
    if (Object.keys(changes).length === 0) {
      onUnchanged()
      return
    }
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    setServerErrors(NO_FIELDS)
    try {
      onSaved(await updateMyProfile(changes))
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
    void save()
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
      {failure && (
        <AccountFailureNotice
          failure={failure}
          refusedTitle="We could not save those details"
          faultHeading="We could not save your details"
          fieldsAreShown={fieldsAreShown}
          otherMessages={otherFieldMessages(serverErrors, PROFILE_FIELD_ORDER)}
          onRetry={() => void save()}
        />
      )}
      <TextField
        {...control('fullName')}
        label="Full name"
        autoComplete="name"
        help="As it appears on your identity document."
        required
      />
      <TextField
        {...control('phone')}
        label="Mobile number"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        required
      />
      <TextField
        {...control('companyName')}
        label="Company name"
        autoComplete="organization"
        help={
          profile.customerType === 'TRADE'
            ? 'The company your trade account is in the name of.'
            : 'Leave this empty unless you hire for a company.'
        }
      />
      <TextField
        {...control('vatNumber')}
        label="VAT number"
        autoComplete="off"
        help="Leave this empty if the company is not registered for VAT."
      />
      <TextField
        {...control('billingAddressLine1')}
        label="Billing address, first line"
        autoComplete="address-line1"
        required
      />
      <div className="grid gap-md sm:grid-cols-2">
        <TextField
          {...control('billingSuburb')}
          label="Billing suburb"
          autoComplete="address-level2"
          required
        />
        <TextField
          {...control('billingCity')}
          label="Billing city"
          autoComplete="address-level1"
          required
        />
      </div>
      <div className="max-w-[12rem]">
        <TextField
          {...control('billingPostalCode')}
          label="Postal code"
          inputMode="numeric"
          autoComplete="postal-code"
          required
        />
      </div>
      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-lg" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {busy ? 'Saving your details' : 'Save these details'}
        </button>
        <button type="button" className="btn-secondary px-md" disabled={busy} onClick={onDiscard}>
          Discard the changes
        </button>
      </div>
      <p className="sr-only" role="status">
        {busy ? 'Saving your details, please wait' : ''}
      </p>
    </form>
  )
}
