/**
 * What SC-23 shows, read from the address and written back to it.
 *
 * The screen has two views, the staff accounts and the customer holds, and the
 * one on the screen is in the address as `view`. The plain address is the
 * staff accounts. The filters of the view and its page live in the address too,
 * under the names the API takes, so a reload or a shared link shows the same
 * page. A switch of view starts the other view afresh, so the address only
 * ever names what is on the screen.
 *
 * A filter the address names is passed to the server as it stands, apart from
 * a role, a standing or a yes or no the API does not have and a page that is
 * not a whole number from one, which are left out. Whether a search makes
 * sense is the server's to say, with a 422 that the screen puts under the box.
 */

import { CUSTOMER_HOLD_PAGE_SIZE } from '../../shared/api/admin-customers'
import { STAFF_ROLES, USER_PAGE_SIZE } from '../../shared/api/admin-users'
import { ACCOUNT_STATUSES } from '../../shared/api/account'
import type { AccountStatus, AdminCustomerQuery, AdminUserQuery, StaffRole } from '../../shared/api/contract'
import { FIRST_PAGE } from './report-address'

/** The two views of the screen. */
export type UsersView = 'staff' | 'customers'

/** The names the screen keeps in the address. */
export const USERS_PARAMETER = {
  view: 'view',
  q: 'q',
  role: 'role',
  active: 'active',
  status: 'status',
  page: 'page',
} as const

/** The value of `view` for the customer holds. The staff accounts have none. */
export const CUSTOMERS_VIEW = 'customers'

/** How a yes or no is written in the address, the way the API takes it. */
const YES = 'true'
const NO = 'false'

/** The filters of the staff accounts that have a control on the screen, by
 *  the names the server gives them. A refusal of any other is listed apart. */
export const STAFF_FILTER_FIELDS: readonly string[] = [USERS_PARAMETER.q, USERS_PARAMETER.role, USERS_PARAMETER.active]

/** The filters of the customer holds that have a control on the screen. */
export const HOLD_FILTER_FIELDS: readonly string[] = [USERS_PARAMETER.q, USERS_PARAMETER.status]

/** What the staff accounts show. A filter that is null is not applied. */
export interface StaffFilters {
  q: string | null
  role: StaffRole | null
  /** True for the accounts that can sign in, false for those that cannot. */
  active: boolean | null
  page: number
}

/** What the customer holds show. No standing means every customer. */
export interface HoldFilters {
  q: string | null
  status: AccountStatus | null
  page: number
}

export const NO_STAFF_FILTERS: StaffFilters = { q: null, role: null, active: null, page: FIRST_PAGE }

function readFilter(value: string | null): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

function readYesOrNo(value: string | null): boolean | null {
  if (value === YES) return true
  if (value === NO) return false
  return null
}

/** Which view the address names. Anything but the customer holds is the staff. */
export function readView(params: URLSearchParams): UsersView {
  return params.get(USERS_PARAMETER.view) === CUSTOMERS_VIEW ? 'customers' : 'staff'
}

/** Read the filters of the staff accounts from the address. */
export function readStaffFilters(params: URLSearchParams): StaffFilters {
  const role = params.get(USERS_PARAMETER.role)
  return {
    q: readFilter(params.get(USERS_PARAMETER.q)),
    role: STAFF_ROLES.find((known) => known === role) ?? null,
    active: readYesOrNo(params.get(USERS_PARAMETER.active)),
    page: readPage(params.get(USERS_PARAMETER.page)),
  }
}

/** Write the staff accounts as an address. A filter not applied and the first page are left out. */
export function writeStaffFilters(filters: StaffFilters): URLSearchParams {
  const written = new URLSearchParams()
  if (filters.q !== null) written.set(USERS_PARAMETER.q, filters.q)
  if (filters.role !== null) written.set(USERS_PARAMETER.role, filters.role)
  if (filters.active !== null) written.set(USERS_PARAMETER.active, filters.active ? YES : NO)
  if (filters.page > FIRST_PAGE) written.set(USERS_PARAMETER.page, String(filters.page))
  return written
}

/** Whether any filter of the staff accounts is applied, the page aside. */
export function staffAreFiltered(filters: StaffFilters): boolean {
  return filters.q !== null || filters.role !== null || filters.active !== null
}

/** The query for one page of the staff accounts. */
export function staffQueryFor(filters: StaffFilters): AdminUserQuery {
  return {
    q: filters.q ?? undefined,
    role: filters.role ?? undefined,
    active: filters.active ?? undefined,
    page: filters.page,
    pageSize: USER_PAGE_SIZE,
  }
}

/** Read the filters of the customer holds from the address. */
export function readHoldFilters(params: URLSearchParams): HoldFilters {
  const status = params.get(USERS_PARAMETER.status)
  return {
    q: readFilter(params.get(USERS_PARAMETER.q)),
    status: ACCOUNT_STATUSES.find((known) => known === status) ?? null,
    page: readPage(params.get(USERS_PARAMETER.page)),
  }
}

/** Write the customer holds as an address, which always names its view. */
export function writeHoldFilters(filters: HoldFilters): URLSearchParams {
  const written = new URLSearchParams()
  written.set(USERS_PARAMETER.view, CUSTOMERS_VIEW)
  if (filters.status !== null) written.set(USERS_PARAMETER.status, filters.status)
  if (filters.q !== null) written.set(USERS_PARAMETER.q, filters.q)
  if (filters.page > FIRST_PAGE) written.set(USERS_PARAMETER.page, String(filters.page))
  return written
}

/** The query for one page of the customer holds. */
export function holdQueryFor(filters: HoldFilters): AdminCustomerQuery {
  return {
    status: filters.status ?? undefined,
    q: filters.q ?? undefined,
    page: filters.page,
    pageSize: CUSTOMER_HOLD_PAGE_SIZE,
  }
}

/**
 * The address of the screen on one view, from its first page. The customer
 * holds open on the customers who are on hold, because those are the ones
 * waiting on the owner.
 */
export function usersViewHref(path: string, view: UsersView): string {
  return view === 'staff' ? path : holdsHref(path, 'ON_HOLD')
}

/** The address of the customer holds showing one standing, from the first page. */
export function holdsHref(path: string, status: AccountStatus | null): string {
  return `${path}?${writeHoldFilters({ q: null, status, page: FIRST_PAGE }).toString()}`
}
