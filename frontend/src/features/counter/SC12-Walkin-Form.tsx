/**
 * Walk-in registration, for SC-12.
 *
 * This form is filled in with a customer standing at the counter and a
 * queue behind them, so it asks for the least that will let a hire go out
 * legally: a name, a number to reach them on, and an identity document
 * against the deposit. Everything else can be added later from the
 * customer's own account.
 */

import { useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import { UserPlus } from 'lucide-react'
import { Card, Field, Notice } from '../../shared/ui'
import { TODAY } from '../../shared/fixtures'
import type { CustomerProfile } from '../../shared/types'

type IdDocType = CustomerProfile['idDocType']

const ID_DOC_LABELS: Record<IdDocType, string> = {
  SA_ID: 'South African ID',
  PASSPORT: 'Passport',
  DRIVING_LICENCE: 'Driving licence',
}

const SA_ID_DIGITS = 13
const SA_MOBILE_DIGITS = 10

interface Draft {
  name: string
  phone: string
  email: string
  idDocType: IdDocType
  idDocNumber: string
  billingSuburb: string
}

const BLANK: Draft = {
  name: '',
  phone: '',
  email: '',
  idDocType: 'SA_ID',
  idDocNumber: '',
  billingSuburb: '',
}

function digitsOnly(value: string): string {
  return value.replace(/\D/g, '')
}

/** Errors say what is wrong and what to do about it, never just "invalid". */
function validate(draft: Draft, existing: CustomerProfile[]): Partial<Record<keyof Draft, string>> {
  const errors: Partial<Record<keyof Draft, string>> = {}

  if (draft.name.trim().length < 2) {
    errors.name = 'Enter the full name as it appears on the identity document.'
  }

  const phone = digitsOnly(draft.phone)
  if (phone.length === 0) {
    errors.phone = 'A mobile number is needed so we can reach them about the hire.'
  } else if (phone.length !== SA_MOBILE_DIGITS || !phone.startsWith('0')) {
    errors.phone = 'Enter a 10 digit South African mobile number, for example 082 441 7719.'
  } else {
    const clash = existing.find((c) => digitsOnly(c.phone) === phone)
    if (clash) {
      errors.phone = `This number is already on file for ${clash.name}. Search for them instead of adding a second record.`
    }
  }

  if (draft.email.trim().length > 0 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) {
    errors.email = 'Check the email address. It needs an @ and a domain, like name@example.co.za.'
  }

  const idNumber = draft.idDocNumber.trim()
  if (idNumber.length === 0) {
    errors.idDocNumber = 'The deposit is taken against an identity document, so this is needed.'
  } else if (draft.idDocType === 'SA_ID' && digitsOnly(idNumber).length !== SA_ID_DIGITS) {
    errors.idDocNumber = 'A South African ID number is 13 digits. Check the number or change the document type.'
  }

  if (draft.billingSuburb.trim().length === 0) {
    errors.billingSuburb = 'Enter the suburb, so the branch knows how far the tools are travelling.'
  }

  return errors
}

export default function WalkinForm({
  existing,
  nameInputRef,
  onRegistered,
}: {
  existing: CustomerProfile[]
  nameInputRef: RefObject<HTMLInputElement | null>
  onRegistered: (customer: CustomerProfile) => void
}) {
  const [draft, setDraft] = useState<Draft>(BLANK)
  const [errors, setErrors] = useState<Partial<Record<keyof Draft, string>>>({})
  const [showSummary, setShowSummary] = useState(false)

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = validate(draft, existing)
    setErrors(found)
    setShowSummary(Object.keys(found).length > 0)
    if (Object.keys(found).length > 0) return

    onRegistered({
      id: `cu-walkin-${digitsOnly(draft.phone)}`,
      name: draft.name.trim(),
      email: draft.email.trim(),
      phone: draft.phone.trim(),
      idDocType: draft.idDocType,
      idDocNumber: draft.idDocNumber.trim(),
      billingSuburb: draft.billingSuburb.trim(),
      billingCity: 'Cape Town',
      onHold: false,
      joinedOn: TODAY,
    })
    setDraft(BLANK)
    setErrors({})
  }

  return (
    <Card title="Register a walk-in">
      <form onSubmit={handleSubmit} noValidate>
        {showSummary && (
          <div className="mb-md">
            <Notice tone="error" title="This customer has not been added yet">
              <p>
                {Object.keys(errors).length} {Object.keys(errors).length === 1 ? 'field needs' : 'fields need'}{' '}
                fixing below. Nothing has been lost, the details you typed are still here.
              </p>
            </Notice>
          </div>
        )}

        <div className="grid gap-md md:grid-cols-2">
          <Field label="Full name" htmlFor="walkin-name" error={errors.name}>
            <input
              id="walkin-name"
              ref={nameInputRef}
              className="field-input"
              value={draft.name}
              autoComplete="name"
              onChange={(event) => update('name', event.target.value)}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? 'walkin-name-error' : undefined}
            />
          </Field>

          <Field
            label="Mobile number"
            htmlFor="walkin-phone"
            help="How we reach them if the hire runs late."
            error={errors.phone}
          >
            <input
              id="walkin-phone"
              type="tel"
              inputMode="numeric"
              className="field-input tabular"
              value={draft.phone}
              autoComplete="tel"
              placeholder="082 441 7719"
              onChange={(event) => update('phone', event.target.value)}
              aria-invalid={Boolean(errors.phone)}
              aria-describedby={errors.phone ? 'walkin-phone-error' : 'walkin-phone-help'}
            />
          </Field>

          <Field
            label="Email address"
            htmlFor="walkin-email"
            help="Optional. Needed to email a booking confirmation."
            error={errors.email}
          >
            <input
              id="walkin-email"
              type="email"
              className="field-input"
              value={draft.email}
              autoComplete="email"
              onChange={(event) => update('email', event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'walkin-email-error' : 'walkin-email-help'}
            />
          </Field>

          <Field label="Identity document" htmlFor="walkin-doc-type">
            <select
              id="walkin-doc-type"
              className="field-input cursor-pointer"
              value={draft.idDocType}
              onChange={(event) => update('idDocType', event.target.value as IdDocType)}
            >
              {(Object.keys(ID_DOC_LABELS) as IdDocType[]).map((type) => (
                <option key={type} value={type}>
                  {ID_DOC_LABELS[type]}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Document number" htmlFor="walkin-doc-number" error={errors.idDocNumber}>
            <input
              id="walkin-doc-number"
              className="field-input tabular"
              value={draft.idDocNumber}
              onChange={(event) => update('idDocNumber', event.target.value)}
              aria-invalid={Boolean(errors.idDocNumber)}
              aria-describedby={errors.idDocNumber ? 'walkin-doc-number-error' : undefined}
            />
          </Field>

          <Field
            label="Suburb"
            htmlFor="walkin-suburb"
            help="City is recorded as Cape Town."
            error={errors.billingSuburb}
          >
            <input
              id="walkin-suburb"
              className="field-input"
              value={draft.billingSuburb}
              autoComplete="address-level2"
              onChange={(event) => update('billingSuburb', event.target.value)}
              aria-invalid={Boolean(errors.billingSuburb)}
              aria-describedby={errors.billingSuburb ? 'walkin-suburb-error' : 'walkin-suburb-help'}
            />
          </Field>
        </div>

        <div className="mt-lg flex flex-wrap gap-sm">
          <button type="submit" className="btn-primary">
            <UserPlus className="h-4 w-4" aria-hidden="true" />
            Add customer
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setDraft(BLANK)
              setErrors({})
              setShowSummary(false)
            }}
          >
            Clear the form
          </button>
        </div>
      </form>
    </Card>
  )
}
