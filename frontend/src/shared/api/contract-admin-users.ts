/**
 * The wire types of the owner's staff accounts and customer holds.
 *
 * I wrote these by hand from the contract, because the generated schema does
 * not describe these routes yet. Once the backend half lands and
 * `npm run api:types` brings them into schema.d.ts, each of these is replaced
 * by a type derived from the generated shape, the way every other contract
 * module builds its types. Until then they say exactly what the contract
 * says, and the readers in admin-users.ts and admin-customers.ts check every
 * member of every body against them, so a body that differs fails there with
 * the name of the field.
 *
 * Two values come from the generated schema already, because other routes use
 * them. The roles a staff account can hold are the stored roles less the
 * customer's, and a customer's standing is the one the counter reads.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { AccountStatus } from './contract-account'
import type { IsoTimestamp, Schemas } from './contract-kit'

/** The two roles a staff account can hold, as the API writes them. */
export type StaffRole = Exclude<Schemas['UserRole'], 'CUSTOMER'>

/**
 * One staff account as the owner reads it. `AdminUser` in the contract.
 *
 * `branchCode` names the branch of a member of counter staff and is null for
 * an administrator, who works across every branch. `phone` is null when none
 * was given. `isActive` is false once the account has been deactivated, and a
 * deactivated account cannot sign in. `emailVerified` is true once the person
 * has proved the address. `lastLoginAt` is null for somebody who has never
 * signed in, and `lockedUntil` is the end of a lock after too many failed
 * sign ins, or null. Nothing about a password is ever sent.
 */
export interface AdminUser {
  id: string
  email: string
  fullName: string
  phone: string | null
  role: StaffRole
  branchCode: string | null
  isActive: boolean
  emailVerified: boolean
  lastLoginAt: IsoTimestamp | null
  lockedUntil: IsoTimestamp | null
  createdAt: IsoTimestamp
}

/**
 * The query `GET /api/admin/users` accepts.
 *
 * `q` is part of a name or an email address. `role` narrows the list to one
 * role, and `active` to the accounts that can sign in or to those that
 * cannot. Every filter may be left out. The page and its size are always sent.
 */
export interface AdminUserQuery {
  q?: string
  role?: StaffRole
  active?: boolean
  page: number
  pageSize: number
}

/** `GET /api/admin/users`. One page of the staff and admin accounts. */
export interface AdminUserPage {
  items: AdminUser[]
  page: number
  pageSize: number
  total: number
}

/**
 * The body `POST /api/admin/users` accepts. Exactly these five members, and
 * never a password.
 *
 * `branchCode` is required for counter staff and must be null for an
 * administrator. `phone` is null when none is given. An address another
 * account already has is refused with a 422 naming `email`.
 */
export interface NewStaffAccountRequest {
  email: string
  fullName: string
  phone: string | null
  role: StaffRole
  branchCode: string | null
}

/**
 * What `POST /api/admin/users` answers with, `201`. The new account, and
 * whether the link to choose a password could be handed to the email gateway.
 * When `emailDeliverable` is false the link never left the system, so the
 * person cannot sign in until email is set up and they ask for a new link.
 */
export interface StaffAccountCreated {
  user: AdminUser
  emailDeliverable: boolean
}

/**
 * The body `PATCH /api/admin/users/{id}` accepts. Any of the name, the phone,
 * the role and the branch, and only what changed. Null clears the phone, and
 * the branch is null for an administrator. The address is not among them.
 * Moving the last active administrator to another role is a 409.
 */
export interface StaffAccountChangesRequest {
  fullName?: string
  phone?: string | null
  role?: StaffRole
  branchCode?: string | null
}

/**
 * The body `POST /api/admin/users/{id}/deactivation` accepts. The reason is
 * kept with the audit event. Deactivating the last active administrator, or
 * one's own account, is a 409.
 */
export interface DeactivationRequest {
  reason: string
}

/**
 * The query `GET /api/admin/customers` accepts. `status` narrows the list to
 * one standing and `q` matches a name, a phone number or an email address.
 * Both may be left out. The page and its size are always sent.
 */
export interface AdminCustomerQuery {
  status?: AccountStatus
  q?: string
  page: number
  pageSize: number
}

/**
 * The body `POST /api/admin/customers/{id}/status` accepts. The standing to
 * move the customer to, and why. Releasing a hold leaves the count of
 * bookings the customer did not collect as it is.
 */
export interface CustomerStandingRequest {
  accountStatus: AccountStatus
  reason: string
}
