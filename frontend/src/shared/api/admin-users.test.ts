/**
 * Tests for the staff account and customer hold routes at the level of the
 * call.
 *
 * The readers check every member of an account, so a body that breaks the
 * contract fails with the name of the field. A new account is read with
 * whether its link could be delivered, a change, a deactivation and a
 * reactivation are each read as the account, and a move of a customer's
 * standing is read as the customer the counter uses.
 */

import { describe, expect, it } from 'vitest'
import { createdResponse, jsonResponse, mockApi } from '../../test/api-mock'
import {
  CUSTOMER_HOLDS_ROUTE,
  OPEN_ACCOUNT_ROUTE,
  THABO_ACCOUNT,
  USERS_ROUTE,
  changeAccountRoute,
  deactivationRoute,
  holdPage,
  reactivationRoute,
  standingRoute,
  userPage,
} from '../../test/admin-user-samples'
import { ON_HOLD } from '../../test/counter-samples'
import { failureOf } from '../../test/session-samples'
import { listCustomerHolds, setCustomerStanding } from './admin-customers'
import {
  changeStaffAccount,
  deactivateStaffAccount,
  listStaffAccounts,
  openStaffAccount,
  reactivateStaffAccount,
} from './admin-users'

describe('the staff accounts', () => {
  it('reads every member of a page, nulls included', async () => {
    mockApi({ [USERS_ROUTE]: () => jsonResponse(userPage()) })

    await expect(listStaffAccounts({ page: 1, pageSize: 20 })).resolves.toEqual(userPage())
  })

  it('sends only the filters that are given, a yes or no as the word', async () => {
    const network = mockApi({ [USERS_ROUTE]: () => jsonResponse(userPage()) })

    await listStaffAccounts({ role: 'COUNTER_STAFF', active: false, page: 2, pageSize: 20 })

    expect(network.requests[0].query.toString()).toBe('role=COUNTER_STAFF&active=false&page=2&pageSize=20')
  })

  it.each([
    ['the role of a customer', { ...THABO_ACCOUNT, role: 'CUSTOMER' }, 'role'],
    ['a sign in that is not an instant', { ...THABO_ACCOUNT, lastLoginAt: 'yesterday' }, 'lastLoginAt'],
    ['no moment the account was opened', { ...THABO_ACCOUNT, createdAt: null }, 'createdAt'],
    ['no word on whether it can sign in', { ...THABO_ACCOUNT, isActive: undefined }, 'isActive'],
  ])('refuses %s, naming the field', async (_what, body, field) => {
    mockApi({ [USERS_ROUTE]: () => jsonResponse({ items: [body], page: 1, pageSize: 20, total: 1 }) })

    const failure = await failureOf(listStaffAccounts({ page: 1, pageSize: 20 }))

    expect(failure.kind).toBe('malformed')
    expect(failure.detail).toContain(field)
  })
})

describe('the writes to a staff account', () => {
  it('opens an account and reads the 201 with whether the link could be delivered', async () => {
    mockApi({ [OPEN_ACCOUNT_ROUTE]: () => createdResponse({ user: THABO_ACCOUNT, emailDeliverable: false }) })

    await expect(
      openStaffAccount({ email: THABO_ACCOUNT.email, fullName: THABO_ACCOUNT.fullName, phone: null, role: 'COUNTER_STAFF', branchCode: 'BLV' }),
    ).resolves.toEqual({ user: THABO_ACCOUNT, emailDeliverable: false })
  })

  it('refuses an answer that does not say whether the link could be delivered', async () => {
    mockApi({ [OPEN_ACCOUNT_ROUTE]: () => createdResponse({ user: THABO_ACCOUNT }) })

    const failure = await failureOf(
      openStaffAccount({ email: THABO_ACCOUNT.email, fullName: THABO_ACCOUNT.fullName, phone: null, role: 'COUNTER_STAFF', branchCode: 'BLV' }),
    )

    expect(failure.detail).toContain('emailDeliverable')
  })

  it('reads a change, a deactivation and a reactivation as the account', async () => {
    const off = { ...THABO_ACCOUNT, isActive: false }
    const network = mockApi({
      [changeAccountRoute(THABO_ACCOUNT.id)]: () => jsonResponse(THABO_ACCOUNT),
      [deactivationRoute(THABO_ACCOUNT.id)]: () => jsonResponse(off),
      [reactivationRoute(THABO_ACCOUNT.id)]: () => jsonResponse(THABO_ACCOUNT),
    })

    await expect(changeStaffAccount(THABO_ACCOUNT.id, { phone: null })).resolves.toEqual(THABO_ACCOUNT)
    await expect(deactivateStaffAccount(THABO_ACCOUNT.id, { reason: 'Left the business.' })).resolves.toEqual(off)
    await expect(reactivateStaffAccount(THABO_ACCOUNT.id)).resolves.toEqual(THABO_ACCOUNT)
    expect(network.requests.map((request) => request.body)).toEqual([{ phone: null }, { reason: 'Left the business.' }, undefined])
  })
})

describe('the customer holds', () => {
  it('reads a page of customers the way the counter reads one', async () => {
    const network = mockApi({ [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage()) })

    await expect(listCustomerHolds({ status: 'ON_HOLD', page: 1, pageSize: 20 })).resolves.toEqual(holdPage())
    expect(network.requests[0].query.toString()).toBe('status=ON_HOLD&page=1&pageSize=20')
  })

  it('moves a customer and reads the customer it answers with', async () => {
    const released = { ...ON_HOLD, accountStatus: 'ACTIVE' }
    const network = mockApi({ [standingRoute(ON_HOLD.id)]: () => jsonResponse(released) })

    await expect(setCustomerStanding(ON_HOLD.id, { accountStatus: 'ACTIVE', reason: 'Settled up.' })).resolves.toEqual(released)
    expect(network.requests[0].body).toEqual({ accountStatus: 'ACTIVE', reason: 'Settled up.' })
  })
})
