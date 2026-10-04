/**
 * The fields of a staff account on SC-23, shared by the form that opens one
 * and the form that changes one.
 *
 * The name, the phone, the role and the branch. The form that opens an account
 * also asks for the address the person signs in with, and an account keeps
 * that address, so the form that changes one shows it read only. The branch is
 * asked for counter staff and not shown at all for an administrator, who works
 * across every branch. There is no password anywhere. The person chooses
 * their own from a link.
 */

import type { StaffRole } from '../../shared/api/contract'
import { STAFF_ROLES } from '../../shared/api/admin-users'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { roleHasBranch, staffFieldId } from './staff-form'
import type { StaffDraft, StaffField } from './staff-form'
import { ROLE_HELP, STAFF_ROLE_LABEL } from './staff-words'
import { branchMenu, useBranchList } from './use-branch-list'

const ROLE_OPTIONS = STAFF_ROLES.map((role) => ({ value: role, label: STAFF_ROLE_LABEL[role] }))

const NO_BRANCH = { value: '', label: 'Choose a branch' }

export function StaffFields({
  form,
  draft,
  onChange,
  errorOf,
  disabled,
}: {
  /** Which form the fields are in, so every id on the page stays unique. */
  form: 'new-staff' | 'edit-staff'
  draft: StaffDraft
  onChange: <Field extends StaffField>(field: Field, value: StaffDraft[Field]) => void
  errorOf: (field: StaffField) => string | undefined
  disabled: boolean
}) {
  const branches = useBranchList()
  const id = (field: StaffField) => staffFieldId(form, field)
  return (
    <>
      <TextInput
        id={id('fullName')}
        label="Full name"
        help="As it should read on the counter screens and in the audit trail."
        value={draft.fullName}
        onChange={(value) => onChange('fullName', value)}
        error={errorOf('fullName')}
        disabled={disabled}
        autoComplete="off"
      />
      {form === 'new-staff' && (
        <TextInput
          id={id('email')}
          label="Work email"
          help="What they sign in with. The link to choose their password goes here, and the address cannot change later."
          value={draft.email}
          onChange={(value) => onChange('email', value)}
          error={errorOf('email')}
          disabled={disabled}
          autoComplete="off"
        />
      )}
      <TextInput
        id={id('phone')}
        label="Phone number, if they have one"
        type="tel"
        inputMode="tel"
        value={draft.phone}
        onChange={(value) => onChange('phone', value)}
        error={errorOf('phone')}
        disabled={disabled}
        autoComplete="off"
      />
      <SelectInput
        id={id('role')}
        label="Role"
        help={ROLE_HELP}
        value={draft.role}
        onChange={(value) => onChange('role', STAFF_ROLES.find((role: StaffRole) => role === value) ?? draft.role)}
        options={ROLE_OPTIONS}
        error={errorOf('role')}
        disabled={disabled}
      />
      {roleHasBranch(draft.role) && (
        <SelectInput
          id={id('branchCode')}
          label="Branch they work at"
          value={draft.branchCode}
          onChange={(value) => onChange('branchCode', value)}
          options={branchMenu(branches, NO_BRANCH, draft.branchCode)}
          error={errorOf('branchCode')}
          help={branches.failed ? 'The branches could not be read. Close the form and open it again.' : undefined}
          disabled={disabled}
        />
      )}
    </>
  )
}
