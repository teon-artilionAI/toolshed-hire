/**
 * The customer's own details on SC-09, and the form for correcting them.
 *
 * Name and identity document are deliberately read only. Those are what the
 * counter checks a person against before releasing equipment, so changing
 * them is a branch job with the document in hand, not a self service edit.
 * Contact and billing details are the customer's to fix.
 */

import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Pencil, ShieldCheck } from 'lucide-react'
import { formatDate } from '../../shared/format'
import type { CustomerProfile } from '../../shared/types'
import { Card, Notice } from '../../shared/ui'
import { TextField, isEmailWellFormed, isMobileWellFormed } from './customer-fields'
import { ID_DOC_LABEL } from './customer-labels'

interface ContactDetails {
  email: string
  phone: string
  billingSuburb: string
  billingCity: string
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-sm border-b border-line py-sm last:border-0">
      <dt className="text-sm text-slate-soft">{term}</dt>
      <dd className="text-sm font-medium text-ink">{children}</dd>
    </div>
  )
}

export function AccountProfileCard({ customer }: { customer: CustomerProfile }) {
  const [details, setDetails] = useState<ContactDetails>({
    email: customer.email,
    phone: customer.phone,
    billingSuburb: customer.billingSuburb,
    billingCity: customer.billingCity,
  })
  const [draft, setDraft] = useState<ContactDetails>(details)
  const [editing, setEditing] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [saved, setSaved] = useState(false)

  const errors = {
    email: !draft.email.trim()
      ? 'We send booking confirmations here, so we need an address.'
      : !isEmailWellFormed(draft.email)
        ? 'That email address is missing an @ or a domain. Check it and try again.'
        : undefined,
    phone: !draft.phone.trim()
      ? 'The counter phones this number when a hire is due back.'
      : !isMobileWellFormed(draft.phone)
        ? 'Enter ten digits starting with a zero, for example 082 441 7719.'
        : undefined,
    billingSuburb: !draft.billingSuburb.trim()
      ? 'Enter the suburb we should bill to.'
      : undefined,
    billingCity: !draft.billingCity.trim()
      ? 'Enter the city we should bill to.'
      : undefined,
  }
  const hasErrors = Object.values(errors).some(Boolean)

  function startEditing() {
    setDraft(details)
    setSubmitted(false)
    setSaved(false)
    setEditing(true)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    if (hasErrors) return
    setDetails(draft)
    setEditing(false)
    setSaved(true)
  }

  return (
    <Card
      title="Your details"
      action={
        !editing && (
          <button type="button" className="btn-ghost px-sm" onClick={startEditing}>
            <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
            Edit contact details
          </button>
        )
      }
    >
      {saved && !editing && (
        <div className="mb-md">
          <Notice tone="success" title="Your details have been updated">
            <p>New bookings and reminders will use these from now on.</p>
          </Notice>
        </div>
      )}

      {customer.onHold && (
        <div className="mb-md">
          <Notice tone="error" title="This account is on hold">
            <p>
              New bookings are blocked until a branch manager lifts the hold.
              Speak to any Toolshed Hire counter to sort it out.
            </p>
          </Notice>
        </div>
      )}

      {editing ? (
        <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-md">
          <TextField
            id="account-email"
            label="Email address"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={draft.email}
            onChange={(v) => setDraft({ ...draft, email: v })}
            error={submitted ? errors.email : undefined}
            required
          />
          <TextField
            id="account-phone"
            label="Mobile number"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            value={draft.phone}
            onChange={(v) => setDraft({ ...draft, phone: v })}
            error={submitted ? errors.phone : undefined}
            required
          />
          <div className="grid gap-md sm:grid-cols-2">
            <TextField
              id="account-suburb"
              label="Billing suburb"
              autoComplete="address-level2"
              value={draft.billingSuburb}
              onChange={(v) => setDraft({ ...draft, billingSuburb: v })}
              error={submitted ? errors.billingSuburb : undefined}
              required
            />
            <TextField
              id="account-city"
              label="Billing city"
              autoComplete="address-level1"
              value={draft.billingCity}
              onChange={(v) => setDraft({ ...draft, billingCity: v })}
              error={submitted ? errors.billingCity : undefined}
              required
            />
          </div>
          <div className="flex flex-wrap gap-sm">
            <button type="submit" className="btn-primary px-lg">
              Save these details
            </button>
            <button
              type="button"
              className="btn-secondary px-md"
              onClick={() => setEditing(false)}
            >
              Discard the changes
            </button>
          </div>
        </form>
      ) : (
        <dl>
          <Row term="Name">{customer.name}</Row>
          <Row term="Email address">{details.email}</Row>
          <Row term="Mobile number">
            <span className="tabular">{details.phone}</span>
          </Row>
          <Row term={ID_DOC_LABEL[customer.idDocType]}>
            <span className="font-mono">{customer.idDocNumber}</span>
          </Row>
          <Row term="Billing address">
            {details.billingSuburb}, {details.billingCity}
          </Row>
          <Row term="With us since">{formatDate(customer.joinedOn)}</Row>
          <Row term="Account standing">
            {customer.onHold ? (
              'On hold'
            ) : (
              <span className="inline-flex items-center gap-xs text-status-available">
                <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden="true" />
                Good standing
              </span>
            )}
          </Row>
        </dl>
      )}

      <p className="mt-md text-sm text-slate-soft">
        Your name and identity document can only be changed at a branch, with
        the document in hand, because the counter checks them before releasing
        equipment.
      </p>
    </Card>
  )
}
