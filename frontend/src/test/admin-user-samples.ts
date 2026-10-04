/**
 * The owner's staff accounts and customer holds for tests, shaped the way the
 * contract for user management describes them.
 *
 * Three staff accounts. The signed in owner, `ADMIN` from session-samples.ts,
 * who has signed in before. A counter assistant at Bellville who has never
 * signed in and whose address is not confirmed, locked after failed sign ins
 * until the afternoon of the pinned day. And a counter assistant at Somerset
 * West who was deactivated. The customers are the counter's, one in good
 * standing, one on hold with three bookings not collected, and one blacklisted.
 */

import type { AdminUser, AdminUserPage, CustomerPage, CustomerSummary } from '../shared/api/contract'
import { ON_HOLD, THANDI, WESLEY } from './counter-samples'
import { ADMIN } from './session-samples'

export const USERS_ROUTE = 'GET /api/admin/users'
export const OPEN_ACCOUNT_ROUTE = 'POST /api/admin/users'
export const CUSTOMER_HOLDS_ROUTE = 'GET /api/admin/customers'

export function changeAccountRoute(id: string): string {
  return `PATCH /api/admin/users/${id}`
}

export function deactivationRoute(id: string): string {
  return `POST /api/admin/users/${id}/deactivation`
}

export function reactivationRoute(id: string): string {
  return `POST /api/admin/users/${id}/reactivation`
}

export function standingRoute(id: string): string {
  return `POST /api/admin/customers/${id}/status`
}

/** The signed in owner's own account. */
export const OWNER_ACCOUNT: AdminUser = {
  id: ADMIN.id,
  email: ADMIN.email,
  fullName: ADMIN.fullName,
  phone: '0215550100',
  role: 'ADMIN',
  branchCode: null,
  isActive: true,
  emailVerified: true,
  lastLoginAt: '2026-03-12T07:45:00+02:00',
  lockedUntil: null,
  createdAt: '2024-01-10T09:00:00+02:00',
}

/** A counter assistant at Bellville, never signed in, locked until 14:30. */
export const THABO_ACCOUNT: AdminUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000002',
  email: 'thabo@toolshedhire.co.za',
  fullName: 'Thabo Ncube',
  phone: null,
  role: 'COUNTER_STAFF',
  branchCode: 'BLV',
  isActive: true,
  emailVerified: false,
  lastLoginAt: null,
  lockedUntil: '2026-03-12T14:30:00+02:00',
  createdAt: '2026-03-01T10:00:00+02:00',
}

/** A counter assistant at Somerset West, deactivated. */
export const ANDRE_ACCOUNT: AdminUser = {
  id: '0b0f6f3e-1111-4a2b-9c3d-000000000004',
  email: 'andre@toolshedhire.co.za',
  fullName: 'Andre Klaasen',
  phone: '0821234567',
  role: 'COUNTER_STAFF',
  branchCode: 'SMW',
  isActive: false,
  emailVerified: true,
  lastLoginAt: '2026-02-20T16:05:00+02:00',
  lockedUntil: null,
  createdAt: '2025-05-02T08:00:00+02:00',
}

export function userPage(
  items: AdminUser[] = [OWNER_ACCOUNT, THABO_ACCOUNT, ANDRE_ACCOUNT],
  overrides: Partial<AdminUserPage> = {},
): AdminUserPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}

/** A customer who was blacklisted. */
export const BLACKLISTED: CustomerSummary = {
  ...WESLEY,
  id: '7a1d0c4e-0000-4000-8000-000000000304',
  displayName: 'Riaan van Wyk',
  email: 'riaan@vwconstruct.co.za',
  companyName: 'VW Construct',
  accountStatus: 'BLACKLISTED',
  noShowCount: 1,
}

export const HOLD_CUSTOMERS = { active: THANDI, onHold: ON_HOLD, blacklisted: BLACKLISTED }

export function holdPage(
  items: CustomerSummary[] = [ON_HOLD, THANDI, BLACKLISTED],
  overrides: Partial<CustomerPage> = {},
): CustomerPage {
  return { items, page: 1, pageSize: 20, total: items.length, ...overrides }
}
