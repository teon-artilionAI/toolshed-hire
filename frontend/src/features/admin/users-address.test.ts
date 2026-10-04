/**
 * Tests for what SC-23 keeps in the address. Each view reads back what it
 * wrote, a value the API does not have is left out, and the query for each
 * page carries the page size.
 */

import { describe, expect, it } from 'vitest'
import {
  holdQueryFor,
  holdsHref,
  readHoldFilters,
  readStaffFilters,
  readView,
  staffQueryFor,
  usersViewHref,
  writeHoldFilters,
  writeStaffFilters,
} from './users-address'

describe('the view in the address', () => {
  it('is the staff accounts unless the address names the customer holds', () => {
    expect(readView(new URLSearchParams(''))).toBe('staff')
    expect(readView(new URLSearchParams('view=elsewhere'))).toBe('staff')
    expect(readView(new URLSearchParams('view=customers'))).toBe('customers')
  })

  it('opens the customer holds on the customers who are on hold', () => {
    expect(usersViewHref('/admin/users', 'staff')).toBe('/admin/users')
    expect(usersViewHref('/admin/users', 'customers')).toBe('/admin/users?view=customers&status=ON_HOLD')
    expect(holdsHref('/admin/users', null)).toBe('/admin/users?view=customers')
  })
})

describe('the staff accounts in the address', () => {
  it('reads back what it wrote', () => {
    const filters = { q: 'thabo', role: 'COUNTER_STAFF' as const, active: false, page: 3 }

    expect(readStaffFilters(writeStaffFilters(filters))).toEqual(filters)
    expect(writeStaffFilters(filters).toString()).toBe('q=thabo&role=COUNTER_STAFF&active=false&page=3')
  })

  it('leaves out a role, a yes or no and a page the API does not have', () => {
    expect(readStaffFilters(new URLSearchParams('q=%20%20&role=CUSTOMER&active=maybe&page=-2'))).toEqual({
      q: null,
      role: null,
      active: null,
      page: 1,
    })
  })

  it('asks for a page of twenty with only the filters applied', () => {
    expect(staffQueryFor({ q: null, role: 'ADMIN', active: true, page: 2 })).toEqual({
      q: undefined,
      role: 'ADMIN',
      active: true,
      page: 2,
      pageSize: 20,
    })
  })
})

describe('the customer holds in the address', () => {
  it('reads back what it wrote, and always names its view', () => {
    const filters = { q: 'riaan', status: 'BLACKLISTED' as const, page: 2 }

    expect(readHoldFilters(writeHoldFilters(filters))).toEqual(filters)
    expect(writeHoldFilters({ q: null, status: null, page: 1 }).toString()).toBe('view=customers')
  })

  it('leaves out a standing the API does not have', () => {
    expect(readHoldFilters(new URLSearchParams('view=customers&status=SUSPENDED')).status).toBeNull()
  })

  it('asks for a page of twenty', () => {
    expect(holdQueryFor({ q: null, status: 'ON_HOLD', page: 1 })).toEqual({ status: 'ON_HOLD', q: undefined, page: 1, pageSize: 20 })
  })
})
