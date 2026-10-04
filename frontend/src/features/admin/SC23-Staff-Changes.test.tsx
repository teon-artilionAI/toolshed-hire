/**
 * Tests for changing, deactivating and reactivating a staff account on SC-23,
 * with the network replaced at `fetch`.
 *
 * An account opens above the list with every field. A change sends only what
 * changed and asks first, a move to administrator sends the branch as null,
 * deactivating asks why and says the person is signed out everywhere at once,
 * and reactivating asks first too. A 409 for the last administrator or for
 * one's own account shows the server's sentence, a 403 does the same, a 422
 * goes under its field, each answer is disabled while in flight, and the list
 * is read again after each write.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { branchDateTime } from '../../shared/today'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  ANDRE_ACCOUNT,
  OWNER_ACCOUNT,
  THABO_ACCOUNT,
  USERS_ROUTE,
  changeAccountRoute,
  deactivationRoute,
  reactivationRoute,
} from '../../test/admin-user-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { lastBody, openAccount, openUsers, rowOf } from './SC23-test-kit'

const REASON = 'Left the business at the end of the month.'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('an account opened from the list', () => {
  it('takes focus and shows every field in words', async () => {
    const { user } = await openUsers()
    const account = await openAccount(user, THABO_ACCOUNT.fullName)

    expect(within(account).getByRole('heading', { level: 3 })).toHaveFocus()
    expect(within(account).getByText(THABO_ACCOUNT.email)).toBeVisible()
    expect(within(account).getByText('None given')).toBeVisible()
    expect(within(account).getByText('Bellville')).toBeVisible()
    expect(within(account).getByText('Locked until 12 Mar 2026 at 14:30')).toBeVisible()
    expect(within(account).getByText(branchDateTime(THABO_ACCOUNT.createdAt))).toBeVisible()
    expect(within(account).queryByText(/password/i)).not.toBeInTheDocument()
  })

  it('gives focus back to its button in the list when it is closed', async () => {
    const { user } = await openUsers()
    const account = await openAccount(user, THABO_ACCOUNT.fullName)

    await user.click(within(account).getByRole('button', { name: 'Close the account' }))

    const row = await rowOf(THABO_ACCOUNT.fullName)
    await waitFor(() => expect(within(row).getByRole('button', { name: `Open the account of ${THABO_ACCOUNT.fullName}` })).toHaveFocus())
  })
})

describe('changing an account', () => {
  it('sends only what changed, with the branch as null for a move to administrator, and asks first', async () => {
    const promoted = { ...THABO_ACCOUNT, role: 'ADMIN' as const, branchCode: null }
    const { user, network } = await openUsers({ [changeAccountRoute(THABO_ACCOUNT.id)]: () => jsonResponse(promoted) })
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    const listReads = network.requestsTo(USERS_ROUTE).length
    await user.click(within(account).getByRole('button', { name: 'Change the name, phone, role or branch' }))

    expect(within(account).getByText(`Signs in as ${THABO_ACCOUNT.email}`)).toBeVisible()
    await user.selectOptions(within(account).getByLabelText('Role'), 'Admin and owner')
    expect(within(account).queryByLabelText('Branch they work at')).not.toBeInTheDocument()
    await user.click(within(account).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByRole('heading', { level: 4, name: `Save the changes to the account of ${THABO_ACCOUNT.fullName}?` })).toHaveFocus()
    expect(screen.getByText(/The role changes to admin and owner, with every branch/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const outcome = await screen.findByText(`The account of ${THABO_ACCOUNT.fullName} is saved`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(lastBody(network, changeAccountRoute(THABO_ACCOUNT.id))).toEqual({ role: 'ADMIN', branchCode: null })
    await waitFor(() => expect(network.requestsTo(USERS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('says so and sends nothing when nothing changed', async () => {
    const { user, network } = await openUsers()
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Change the name, phone, role or branch' }))

    await user.click(within(account).getByRole('button', { name: 'Save the changes' }))

    expect(within(account).getByText('Nothing has changed yet')).toBeVisible()
    expect(network.requestsTo(changeAccountRoute(THABO_ACCOUNT.id))).toHaveLength(0)
  })

  it('shows the sentence of a 409 when the last administrator would be moved to another role', async () => {
    const detail = 'Marius Pretorius is the only active administrator, so the role cannot change. Make somebody else an administrator first.'
    const { user, network } = await openUsers({ [changeAccountRoute(OWNER_ACCOUNT.id)]: () => problemResponse(409, { detail }) })
    const account = await openAccount(user, OWNER_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Change the name, phone, role or branch' }))
    await user.selectOptions(within(account).getByLabelText('Role'), 'Counter staff')
    await user.selectOptions(within(account).getByLabelText('Branch they work at'), 'Cape Town CBD')
    await user.click(within(account).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const alert = await within(account).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The changes were not saved')
    expect(alert).toHaveTextContent(detail)
    expect(lastBody(network, changeAccountRoute(OWNER_ACCOUNT.id))).toEqual({ role: 'COUNTER_STAFF', branchCode: 'CBD' })
  })

  it('puts a refused name under its box', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.fullName': 'Give the full name, two characters or more.' } } })
    const { user } = await openUsers({ [changeAccountRoute(THABO_ACCOUNT.id)]: refusal })
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Change the name, phone, role or branch' }))
    await user.clear(within(account).getByLabelText('Full name'))
    await user.type(within(account).getByLabelText('Full name'), 'T')
    await user.click(within(account).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    await waitFor(() =>
      expect(within(account).getByLabelText('Full name')).toHaveAccessibleDescription(
        expect.stringContaining('Give the full name, two characters or more.'),
      ),
    )
  })
})

describe('deactivating and reactivating an account', () => {
  it('asks why, says the person is signed out everywhere at once, and sends the reason', async () => {
    const deactivated = { ...THABO_ACCOUNT, isActive: false }
    const { user, network } = await openUsers({ [deactivationRoute(THABO_ACCOUNT.id)]: () => jsonResponse(deactivated) })
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    const listReads = network.requestsTo(USERS_ROUTE).length
    await user.click(within(account).getByRole('button', { name: 'Deactivate the account' }))

    expect(screen.getByRole('heading', { level: 4, name: `Deactivate the account of ${THABO_ACCOUNT.fullName}?` })).toHaveFocus()
    expect(screen.getByText(/is signed out everywhere at once, on every device/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, deactivate it' }))
    expect(within(account).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('Write the reason'))
    expect(network.requestsTo(deactivationRoute(THABO_ACCOUNT.id))).toHaveLength(0)

    await user.type(within(account).getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, deactivate it' }))

    const outcome = await screen.findByText(`${THABO_ACCOUNT.fullName} can no longer sign in`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(lastBody(network, deactivationRoute(THABO_ACCOUNT.id))).toEqual({ reason: REASON })
    expect(within(account).getByRole('button', { name: 'Reactivate the account' })).toBeVisible()
    await waitFor(() => expect(network.requestsTo(USERS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('shows the sentence of a 409 when the owner tries to deactivate their own account', async () => {
    const detail = 'You cannot deactivate your own account. Ask another administrator to do it.'
    const { user } = await openUsers({ [deactivationRoute(OWNER_ACCOUNT.id)]: () => problemResponse(409, { detail }) })
    const account = await openAccount(user, OWNER_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Deactivate the account' }))
    await user.type(within(account).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, deactivate it' }))

    const alert = await within(account).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The account was not deactivated')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts a refused reason under its box', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.reason': 'Give a reason of 5 to 200 characters.' } } })
    const { user } = await openUsers({ [deactivationRoute(THABO_ACCOUNT.id)]: refusal })
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Deactivate the account' }))
    await user.type(within(account).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, deactivate it' }))

    await waitFor(() =>
      expect(within(account).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('5 to 200 characters')),
    )
    expect(within(account).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openUsers({ [deactivationRoute(THABO_ACCOUNT.id)]: neverAnswers })
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Deactivate the account' }))
    await user.type(within(account).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, deactivate it' }))

    const waiting = await screen.findByRole('button', { name: 'Deactivating it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(deactivationRoute(THABO_ACCOUNT.id))).toHaveLength(1)
  })

  it('puts the question away unanswered and gives focus back to its button', async () => {
    const { user, network } = await openUsers()
    const account = await openAccount(user, THABO_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Deactivate the account' }))

    await user.click(screen.getByRole('button', { name: 'Leave it as it is' }))

    await waitFor(() => expect(within(account).getByRole('button', { name: 'Deactivate the account' })).toHaveFocus())
    expect(network.requestsTo(deactivationRoute(THABO_ACCOUNT.id))).toHaveLength(0)
  })

  it('reactivates a deactivated account after asking, with no body', async () => {
    const reactivated = { ...ANDRE_ACCOUNT, isActive: true }
    const { user, network } = await openUsers({ [reactivationRoute(ANDRE_ACCOUNT.id)]: () => jsonResponse(reactivated) })
    const account = await openAccount(user, ANDRE_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Reactivate the account' }))

    expect(screen.getByRole('heading', { level: 4, name: `Reactivate the account of ${ANDRE_ACCOUNT.fullName}?` })).toHaveFocus()
    expect(within(account).queryByLabelText('Why')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes, reactivate it' }))

    expect(await screen.findByText(`${ANDRE_ACCOUNT.fullName} can sign in again`, {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(reactivationRoute(ANDRE_ACCOUNT.id))).toHaveLength(1)
    expect(lastBody(network, reactivationRoute(ANDRE_ACCOUNT.id))).toBeUndefined()
    expect(within(account).getByRole('button', { name: 'Deactivate the account' })).toBeVisible()
  })

  it('shows the sentence of a 403', async () => {
    const detail = 'Only an administrator may reactivate an account.'
    const { user } = await openUsers({ [reactivationRoute(ANDRE_ACCOUNT.id)]: () => problemResponse(403, { detail }) })
    const account = await openAccount(user, ANDRE_ACCOUNT.fullName)
    await user.click(within(account).getByRole('button', { name: 'Reactivate the account' }))

    await user.click(screen.getByRole('button', { name: 'Yes, reactivate it' }))

    expect(await within(account).findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent(detail)
  })
})
