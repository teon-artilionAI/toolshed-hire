/**
 * The owner's staff accounts. Listing them, opening one, changing its name,
 * phone, role and branch, and deactivating and reactivating it.
 *
 * Every route here is for an administrator, and the API refuses anyone else
 * with a 403. Each function makes one call and reads the body into its
 * contract type, checking every member, so a body that breaks the contract
 * fails here with the name of the field.
 *
 * No route reads or sets a password. A new account gets a link to choose one
 * through the reset flow the customers already use, and the answer says
 * whether that link could be handed to the email gateway. Every rule about who
 * may hold which role, which branch goes with which role and which account may
 * be deactivated is the server's. A refused field comes back as a 422 naming
 * it, and a move the server will not make, such as leaving the business with
 * no active administrator, comes back as a 409 with its sentence. Nothing is
 * ever deleted, so an account leaves by being deactivated. Each write is sent
 * once for each press of a button and never repeated by the client, because a
 * request that timed out may still have reached the server.
 *
 * A change, a deactivation and a reactivation each answer with the account as
 * it now stands, which is what every other write of the owner's answers with,
 * and the screen reads the list again after each one either way. Asking for
 * what the account already is writes nothing and answers with it as it is. A
 * 409 carries the problem type `state-transition` and the server's sentence,
 * and a caller who is no longer an active administrator is refused with a 403.
 */

import { malformedResponse } from '../api-problem'
import { api } from './client'
import type {
  AdminUser,
  AdminUserPage,
  AdminUserQuery,
  DeactivationRequest,
  IsoTimestamp,
  NewStaffAccountRequest,
  StaffAccountChangesRequest,
  StaffAccountCreated,
  StaffRole,
} from './contract'
import {
  readCount,
  readFlag,
  readList,
  readNullableText,
  readNullableTimestamp,
  readObject,
  readOneOf,
  readText,
} from './read'

const USERS_ENDPOINT = '/admin/users'

/** How many accounts a page of the list holds. */
export const USER_PAGE_SIZE = 20

/** The roles a staff account can hold, in the order a menu lists them. */
export const STAFF_ROLES: readonly StaffRole[] = ['COUNTER_STAFF', 'ADMIN']

/** The key is a key by the time it reaches here, but it is encoded all the same. */
function accountPath(id: string): string {
  return `${USERS_ENDPOINT}/${encodeURIComponent(id)}`
}

/** An instant the contract never sends as null. */
function readInstant(record: Record<string, unknown>, key: string, path: string): IsoTimestamp {
  const value = readNullableTimestamp(record, key, path)
  if (value === null) throw malformedResponse(path, `Expected field ${key} from ${path} to be an instant, got null.`)
  return value
}

function readAdminUser(value: unknown, path: string): AdminUser {
  const record = readObject(value, path, 'a staff account')
  return {
    id: readText(record, 'id', path),
    email: readText(record, 'email', path),
    fullName: readText(record, 'fullName', path),
    phone: readNullableText(record, 'phone', path),
    role: readOneOf(record, 'role', path, STAFF_ROLES),
    branchCode: readNullableText(record, 'branchCode', path),
    isActive: readFlag(record, 'isActive', path),
    emailVerified: readFlag(record, 'emailVerified', path),
    lastLoginAt: readNullableTimestamp(record, 'lastLoginAt', path),
    lockedUntil: readNullableTimestamp(record, 'lockedUntil', path),
    createdAt: readInstant(record, 'createdAt', path),
  }
}

function readUserPage(value: unknown, path: string): AdminUserPage {
  const record = readObject(value, path, 'a page of staff accounts')
  return {
    items: readList(record, 'items', path, readAdminUser),
    page: readCount(record, 'page', path),
    pageSize: readCount(record, 'pageSize', path),
    total: readCount(record, 'total', path),
  }
}

function readCreated(value: unknown, path: string): StaffAccountCreated {
  const record = readObject(value, path, 'a new staff account')
  return {
    user: readAdminUser(record.user, path),
    emailDeliverable: readFlag(record, 'emailDeliverable', path),
  }
}

/**
 * GET /api/admin/users. One page of the staff and admin accounts that match.
 * Customers are not among them.
 *
 * @throws ApiError with status 422 naming a filter the server refused, and
 *   403 for anyone but an administrator.
 */
export function listStaffAccounts(query: AdminUserQuery, signal?: AbortSignal): Promise<AdminUserPage> {
  return api.get(USERS_ENDPOINT, readUserPage, { query, signal })
}

/**
 * POST /api/admin/users. Answers 201 with the new account and whether the link
 * to choose a password could be delivered.
 *
 * @throws ApiError with status 422 naming the field the server refused, such
 *   as an address another account already has, and 403 for anyone but an
 *   administrator.
 */
export function openStaffAccount(body: NewStaffAccountRequest): Promise<StaffAccountCreated> {
  return api.post(USERS_ENDPOINT, body, readCreated)
}

/**
 * PATCH /api/admin/users/{id}. Changes the fields sent and leaves the rest.
 *
 * @throws ApiError with status 409 when the change would leave the business
 *   with no active administrator, 422 naming the field refused, 404 when no
 *   account has the key, and 403 for anyone but an administrator.
 */
export function changeStaffAccount(id: string, changes: StaffAccountChangesRequest): Promise<AdminUser> {
  return api.patch(accountPath(id), changes, readAdminUser)
}

/**
 * POST /api/admin/users/{id}/deactivation. Stops the account signing in at
 * once and ends every session it has.
 *
 * @throws ApiError with status 409 for the last active administrator or one's
 *   own account, 422 naming `reason`, 404 when no account has the key, and 403
 *   for anyone but an administrator.
 */
export function deactivateStaffAccount(id: string, body: DeactivationRequest): Promise<AdminUser> {
  return api.post(`${accountPath(id)}/deactivation`, body, readAdminUser)
}

/**
 * POST /api/admin/users/{id}/reactivation. Lets the account sign in again.
 *
 * @throws ApiError with status 404 when no account has the key, and 403 for
 *   anyone but an administrator.
 */
export function reactivateStaffAccount(id: string): Promise<AdminUser> {
  return api.post(`${accountPath(id)}/reactivation`, undefined, readAdminUser)
}
