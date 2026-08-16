/**
 * Creating a staff account, on SC-23.
 *
 * The prototype has no back end, so nothing is written anywhere. What it
 * does have is the real validation, because the rules are the interesting
 * part: staff sign in on a company address, counter staff belong to exactly
 * one branch, and an address can only be used once.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { UserPlus, X } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import type { BranchCode, Role, UserAccount } from '../../shared/types'
import { Field } from '../../shared/ui'

const STAFF_DOMAIN = '@toolshedhire.co.za'
const SELECT_CLASS = 'field-input cursor-pointer transition-colors duration-200'

type StaffRole = Extract<Role, 'counter' | 'admin'>

interface Draft {
  name: string
  email: string
  role: StaffRole
  branchCode: BranchCode | ''
}

const EMPTY: Draft = { name: '', email: '', role: 'counter', branchCode: '' }

type Errors = Partial<Record<keyof Draft, string>>

function validate(draft: Draft, takenEmails: string[]): Errors {
  const errors: Errors = {}
  const name = draft.name.trim()
  const email = draft.email.trim().toLowerCase()

  if (name.length < 2) {
    errors.name = 'Enter the full name as it should appear on the counter screen.'
  }
  if (email.length === 0) {
    errors.email = 'Enter a work email address. It is what they sign in with.'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    errors.email = `That is not a complete address. It should look like name${STAFF_DOMAIN}.`
  } else if (!email.endsWith(STAFF_DOMAIN)) {
    errors.email = `Staff sign in on a company address. Use one ending in ${STAFF_DOMAIN}, or register this person as a customer instead.`
  } else if (takenEmails.includes(email)) {
    errors.email = 'Somebody already has that address. Check the list below, or use a different one.'
  }
  if (draft.role === 'counter' && draft.branchCode === '') {
    errors.branchCode = 'Counter staff work at one branch. Pick the branch they are based at.'
  }
  return errors
}

export default function StaffAccountForm({
  takenEmails,
  onCreate,
  onCancel,
}: {
  takenEmails: string[]
  onCreate: (account: Omit<UserAccount, 'id'>) => void
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [errors, setErrors] = useState<Errors>({})
  const [submitted, setSubmitted] = useState(false)

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    if (submitted) setErrors(validate(next, takenEmails))
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    const found = validate(draft, takenEmails)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    onCreate({
      name: draft.name.trim(),
      email: draft.email.trim().toLowerCase(),
      role: draft.role,
      branchCode: draft.role === 'counter' ? (draft.branchCode as BranchCode) : undefined,
      active: true,
    })
    setDraft(EMPTY)
    setSubmitted(false)
    setErrors({})
  }

  return (
    <form noValidate onSubmit={handleSubmit}>
      <div className="grid gap-md sm:grid-cols-2">
        <Field label="Full name" htmlFor="staff-name" error={errors.name}>
          <input
            id="staff-name"
            className="field-input"
            value={draft.name}
            autoComplete="off"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? 'staff-name-error' : undefined}
            onChange={(e) => set('name', e.target.value)}
          />
        </Field>

        <Field
          label="Work email"
          htmlFor="staff-email"
          help={`Staff sign in on a ${STAFF_DOMAIN} address.`}
          error={errors.email}
        >
          <input
            id="staff-email"
            type="email"
            className="field-input"
            value={draft.email}
            autoComplete="off"
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={errors.email ? 'staff-email-error' : 'staff-email-help'}
            onChange={(e) => set('email', e.target.value)}
          />
        </Field>

        <Field
          label="Role"
          htmlFor="staff-role"
          help="Counter staff work the branch. Admins also see reports, pricing and this screen."
        >
          <select
            id="staff-role"
            className={SELECT_CLASS}
            value={draft.role}
            aria-describedby="staff-role-help"
            onChange={(e) => set('role', e.target.value as StaffRole)}
          >
            <option value="counter">Counter staff</option>
            <option value="admin">Admin and owner</option>
          </select>
        </Field>

        <Field
          label="Branch"
          htmlFor="staff-branch"
          help={
            draft.role === 'admin'
              ? 'Admins see all three branches, so a branch is optional.'
              : undefined
          }
          error={errors.branchCode}
        >
          <select
            id="staff-branch"
            className={SELECT_CLASS}
            value={draft.branchCode}
            aria-invalid={errors.branchCode ? true : undefined}
            onChange={(e) => set('branchCode', e.target.value as BranchCode | '')}
          >
            <option value="">
              {draft.role === 'admin' ? 'All three branches' : 'Choose a branch'}
            </option>
            {branches.map((b) => (
              <option key={b.code} value={b.code}>
                {b.name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="mt-lg flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
          Create the account
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary px-md">
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  )
}
