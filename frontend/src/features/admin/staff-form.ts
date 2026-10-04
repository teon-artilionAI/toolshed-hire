/**
 * The two forms of the staff accounts on SC-23, opening an account and
 * changing one, and the bodies they are sent as.
 *
 * Every field carries the name the API gives it, so a message the API sends
 * about a field lands under that field with no table in between.
 *
 * The browser holds no copy of the rules about names, addresses or phone
 * numbers. An empty name, an address that is not one, and an address another
 * account already has are the server's to refuse, and its 422 puts each
 * sentence under its field. The forms only check what they need to write a
 * body at all. Counter staff work at one branch, so a branch has to be chosen
 * for them, and an administrator has none, so their branch is sent as null.
 *
 * Neither form has a password. The person chooses their own from a link.
 */

import type { AdminUser, NewStaffAccountRequest, StaffAccountChangesRequest, StaffRole } from '../../shared/api/contract'

/** What the owner is typing, one string for each field and the role. */
export interface StaffDraft {
  fullName: string
  email: string
  phone: string
  role: StaffRole
  branchCode: string
}

export type StaffField = keyof StaffDraft

/** The fields an existing account can change. The address is not among them. */
export type StaffChangesField = Exclude<StaffField, 'email'>

export type StaffDraftErrors = Partial<Record<StaffField, string>>

/** Reading order of the form that opens an account, which is also the order problems are listed in. */
export const NEW_STAFF_FIELD_ORDER: readonly StaffField[] = ['fullName', 'email', 'phone', 'role', 'branchCode']

/** Reading order of the form that changes an account. */
export const STAFF_CHANGES_FIELD_ORDER: readonly StaffChangesField[] = ['fullName', 'phone', 'role', 'branchCode']

const CHOOSE_A_BRANCH = 'Choose the branch they work at. Counter staff work at one branch.'

/** A new account, with nothing filled in. Most new accounts are counter staff. */
export const EMPTY_STAFF_DRAFT: StaffDraft = { fullName: '', email: '', phone: '', role: 'COUNTER_STAFF', branchCode: '' }

/** The id of the control for a field, which a problem above the form links to. */
export function staffFieldId(form: 'new-staff' | 'edit-staff', field: StaffField): string {
  return `${form}-${field}`
}

/** The id of the button that opens an account from the list, so focus can come
 *  back to it when the account is closed. */
export function openAccountButtonId(id: string): string {
  return `open-account-${id}`
}

/** Whether the role works at one branch, so a branch is asked for. */
export function roleHasBranch(role: StaffRole): boolean {
  return role === 'COUNTER_STAFF'
}

function optionalText(typed: string): string | null {
  const trimmed = typed.trim()
  return trimmed === '' ? null : trimmed
}

/** The branch to send for a role, or undefined when one is needed and none was chosen. */
function branchFor(draft: Pick<StaffDraft, 'role' | 'branchCode'>): string | null | undefined {
  if (!roleHasBranch(draft.role)) return null
  return draft.branchCode === '' ? undefined : draft.branchCode
}

/** Either the body to send, or why the form cannot be written as one yet. */
export type CheckedStaff<Body> = { body: Body; errors: null } | { body: null; errors: StaffDraftErrors }

/** The body of a new account, with exactly the five fields the route takes. */
export function newStaffRequestFrom(draft: StaffDraft): CheckedStaff<NewStaffAccountRequest> {
  const branchCode = branchFor(draft)
  if (branchCode === undefined) return { body: null, errors: { branchCode: CHOOSE_A_BRANCH } }
  return {
    errors: null,
    body: {
      email: draft.email.trim(),
      fullName: draft.fullName.trim(),
      phone: optionalText(draft.phone),
      role: draft.role,
      branchCode,
    },
  }
}

/** The form for an account that exists, holding what the server holds. */
export function draftOfAccount(user: AdminUser): StaffDraft {
  return {
    fullName: user.fullName,
    email: user.email,
    phone: user.phone ?? '',
    role: user.role,
    branchCode: user.branchCode ?? '',
  }
}

/**
 * The body of a change, with only the fields that differ from what the server
 * holds. A move to administrator sends the branch as null, because an
 * administrator has none. An empty body means nothing was changed.
 */
export function staffChangesFrom(user: AdminUser, draft: StaffDraft): CheckedStaff<StaffAccountChangesRequest> {
  const branchCode = branchFor(draft)
  if (branchCode === undefined) return { body: null, errors: { branchCode: CHOOSE_A_BRANCH } }
  const changes: StaffAccountChangesRequest = {}
  const fullName = draft.fullName.trim()
  if (fullName !== user.fullName) changes.fullName = fullName
  const phone = optionalText(draft.phone)
  if (phone !== user.phone) changes.phone = phone
  if (draft.role !== user.role) changes.role = draft.role
  if (branchCode !== user.branchCode) changes.branchCode = branchCode
  return { body: changes, errors: null }
}
