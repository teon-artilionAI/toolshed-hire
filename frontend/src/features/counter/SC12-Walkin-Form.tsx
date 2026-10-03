/**
 * Walk in registration, for SC-12.
 *
 * The form is checked when it is sent, and every problem is listed above it
 * and shown under its own field. It is sent once for each press of the button,
 * and the button is disabled while the request is in flight. A 422 puts each
 * of the server's sentences under the field it names, until that field is
 * changed. Anything else is the shared error state with a way to try again.
 *
 * The rules and the body are in walkin-form.ts.
 */

import { useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Loader2, UserPlus } from 'lucide-react'
import { ID_DOCUMENT_LAST_LENGTH, ID_DOCUMENT_TYPES, CUSTOMER_TYPES } from '../../shared/api/account'
import type { CustomerSummary } from '../../shared/api/contract'
import { rememberCustomer } from '../../shared/api/counter-queries'
import { registerWalkIn } from '../../shared/api/customers'
import { logEvent } from '../../shared/api/log'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { ErrorState } from '../../shared/async-states'
import { Card, Notice } from '../../shared/ui'
import { CUSTOMER_TYPE_LABEL, ID_DOCUMENT_LABEL } from './counter-labels'
import { ProblemList, SelectInput, TextInput } from './counter-fields'
import { describeCounterFailure } from './counter-refusal'
import type { CounterRefusal } from './counter-refusal'
import {
  EMPTY_WALK_IN,
  POSTAL_CODE_DIGITS,
  WALK_IN_FIELD_ORDER,
  toWalkInRequest,
  validateWalkIn,
  withValue,
} from './walkin-form'
import type { WalkInField, WalkInForm } from './walkin-form'

const NO_SERVER_ERRORS: FieldErrors = {}

const FAILURE_HEADING = 'We could not add the customer'

/**
 * Why the last send did not work. A refusal whose every message sits under a
 * field says nothing more here, because the fields say it better.
 */
function FailureNotice({
  failure,
  fieldsAreShown,
  leftOver,
  onRetry,
}: {
  failure: CounterRefusal
  fieldsAreShown: boolean
  leftOver: readonly string[]
  onRetry: () => void
}) {
  if (failure.kind === 'fault') {
    return (
      <div className="mb-md">
        <ErrorState heading={FAILURE_HEADING} error={failure.error} onRetry={onRetry} />
      </div>
    )
  }
  const quiet = failure.kind === 'refused' && fieldsAreShown && leftOver.length === 0
  if (quiet) return null
  return (
    <div className="mb-md">
      <Notice tone="error" title={FAILURE_HEADING}>
        {!(failure.kind === 'refused' && fieldsAreShown) && <p>{failure.detail}</p>}
        {leftOver.length > 0 && (
          <ul className="mt-xs list-disc pl-lg">
            {leftOver.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}
      </Notice>
    </div>
  )
}

const ID_DOCUMENT_OPTIONS = ID_DOCUMENT_TYPES.map((type) => ({ value: type, label: ID_DOCUMENT_LABEL[type] }))
const CUSTOMER_TYPE_OPTIONS = CUSTOMER_TYPES.map((type) => ({ value: type, label: CUSTOMER_TYPE_LABEL[type] }))

export default function WalkinForm({
  branchCode,
  branchName,
  nameInputRef,
  onRegistered,
}: {
  /** Sent with the walk in. Null for counter staff, the chosen branch for an administrator. */
  branchCode: string | null
  /** The branch the walk in is registered at, for the words on the form. */
  branchName: string
  nameInputRef: RefObject<HTMLInputElement | null>
  onRegistered: (customer: CustomerSummary) => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<WalkInForm>(EMPTY_WALK_IN)
  const [submitted, setSubmitted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<CounterRefusal | null>(null)
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_SERVER_ERRORS)
  // State lands after the event that set it. This flag is set in the same tick
  // as the request, so a second press can never start another.
  const inFlight = useRef(false)

  const clientErrors = validateWalkIn(form)
  const trade = form.customerType === 'TRADE'
  const shownFields = WALK_IN_FIELD_ORDER.filter(
    (field) => trade || (field !== 'companyName' && field !== 'vatNumber'),
  )
  const problems = shownFields.flatMap((field) => {
    const message = serverErrors[field] || (submitted ? clientErrors[field] : undefined)
    return message ? [{ id: `walkin-${field}`, message }] : []
  })

  function errorFor(field: WalkInField): string | undefined {
    return serverErrors[field] || (submitted ? clientErrors[field] : undefined)
  }

  function change(field: WalkInField, value: string) {
    setForm((current) => withValue(current, field, value))
    if (serverErrors[field]) {
      setServerErrors((current) =>
        Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)),
      )
    }
  }

  function control(field: WalkInField) {
    return {
      id: `walkin-${field}`,
      value: form[field],
      onChange: (value: string) => change(field, value),
      error: errorFor(field),
      disabled: busy,
    }
  }

  async function send(): Promise<void> {
    setSubmitted(true)
    if (Object.keys(clientErrors).length > 0 || inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setFailure(null)
    setServerErrors(NO_SERVER_ERRORS)
    try {
      const customer = await registerWalkIn(toWalkInRequest(form, branchCode))
      logEvent('info', 'counter.walk_in_registered', { customer_id: customer.id })
      rememberCustomer(queryClient, customer)
      setForm(EMPTY_WALK_IN)
      setSubmitted(false)
      onRegistered(customer)
    } catch (cause) {
      const described = describeCounterFailure(cause)
      setFailure(described)
      if (described.kind === 'refused') setServerErrors(described.fields)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send()
  }

  const leftOver =
    failure?.kind === 'refused' ? otherFieldMessages(serverErrors, shownFields) : []

  return (
    <Card title="Register a walk in">
      <form onSubmit={handleSubmit} noValidate aria-label="Register a walk in">
        <p className="mb-md text-sm text-slate-soft">
          For a customer with no account. They are registered at {branchName} with no login, and
          can be booked for straight away.
        </p>

        {problems.length > 0 && (
          <div className="mb-md">
            <Notice
              tone="error"
              title={`This customer has not been added yet. ${problems.length} ${
                problems.length === 1 ? 'answer needs' : 'answers need'
              } fixing.`}
            >
              <ProblemList problems={problems} />
            </Notice>
          </div>
        )}
        {failure !== null && (
          <FailureNotice
            failure={failure}
            fieldsAreShown={problems.length > 0}
            leftOver={leftOver}
            onRetry={() => void send()}
          />
        )}

        <div className="grid gap-md md:grid-cols-2">
          <TextInput
            {...control('displayName')}
            label="Full name"
            help="As it is written on the identity document."
            autoComplete="off"
            inputRef={nameInputRef}
          />
          <TextInput
            {...control('phone')}
            label="Mobile number"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            placeholder="082 441 7719"
          />
          <SelectInput {...control('customerType')} label="Kind of customer" options={CUSTOMER_TYPE_OPTIONS} />
          {trade && (
            <>
              <TextInput {...control('companyName')} label="Company name" autoComplete="off" />
              <TextInput {...control('vatNumber')} label="VAT number" help="Optional." autoComplete="off" />
            </>
          )}
          <SelectInput {...control('idDocumentType')} label="Identity document" options={ID_DOCUMENT_OPTIONS} />
          <TextInput
            {...control('idDocumentLast4')}
            label="Last four characters of the document number"
            help="Check the full document in your hand, then type only its last four characters. The whole number is never kept."
            maxLength={ID_DOCUMENT_LAST_LENGTH}
            autoComplete="off"
          />
          <TextInput {...control('billingAddressLine1')} label="Billing address, first line" autoComplete="off" />
          <TextInput {...control('billingSuburb')} label="Billing suburb" autoComplete="off" />
          <TextInput {...control('billingCity')} label="Billing city" autoComplete="off" />
          <TextInput
            {...control('billingPostalCode')}
            label="Postal code"
            inputMode="numeric"
            maxLength={POSTAL_CODE_DIGITS}
            autoComplete="off"
          />
        </div>

        <div className="mt-lg flex flex-wrap gap-sm">
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            {busy ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
            ) : (
              <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            {busy ? 'Adding the customer' : 'Add this customer'}
          </button>
        </div>
        <p className="sr-only" role="status">
          {busy ? 'Adding the customer, please wait' : ''}
        </p>
      </form>
    </Card>
  )
}
