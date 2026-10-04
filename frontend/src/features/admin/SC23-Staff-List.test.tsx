/**
 * Tests for the staff accounts on SC-23, with the network replaced at `fetch`.
 *
 * The list is one paged read with a search and two filters. Waiting, failed,
 * empty and loaded, every value as the server sent it and in words, the search
 * and the filters in the address and in the query, a refusal under its
 * control, and paging.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { ANDRE_ACCOUNT, OWNER_ACCOUNT, THABO_ACCOUNT, USERS_ROUTE, userPage } from '../../test/admin-user-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { USERS, findAccounts, lastAsked, openUsers, rowOf } from './SC23-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function accountsRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'The staff accounts' })
}

describe('reading the staff accounts', () => {
  it('is connected, and shows every account as the server sent it, in words', async () => {
    const { network } = await openUsers()
    await findAccounts()

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(lastAsked(network, USERS_ROUTE).toString()).toBe('page=1&pageSize=20')
    expect(within(accountsRegion()).getByText('3 accounts match.')).toBeVisible()

    const owner = await rowOf(OWNER_ACCOUNT.fullName)
    expect(within(owner).getByText('(you)')).toBeVisible()
    expect(within(owner).getByText(OWNER_ACCOUNT.email)).toBeVisible()
    expect(within(owner).getByText('Admin and owner')).toBeVisible()
    expect(within(owner).getByText('Every branch')).toBeVisible()
    expect(within(owner).getByText('Can sign in', { selector: '.pill' })).toBeVisible()
    expect(within(owner).getByText('Confirmed')).toBeVisible()
    expect(within(owner).getByText('Not locked')).toBeVisible()
    expect(within(owner).getByText('12 Mar 2026 at 07:45')).toBeVisible()

    const thabo = await rowOf(THABO_ACCOUNT.fullName)
    expect(within(thabo).queryByText('(you)')).not.toBeInTheDocument()
    expect(within(thabo).getByText('Counter staff')).toBeVisible()
    expect(within(thabo).getByText('Bellville')).toBeVisible()
    expect(within(thabo).getByText('Not confirmed yet')).toBeVisible()
    expect(within(thabo).getByText('Locked until 12 Mar 2026 at 14:30')).toBeVisible()
    expect(within(thabo).getByText('Never signed in')).toBeVisible()

    const andre = await rowOf(ANDRE_ACCOUNT.fullName)
    expect(within(andre).getByText('Somerset West')).toBeVisible()
    expect(within(andre).getByText('Deactivated', { selector: '.pill' })).toBeVisible()
  })

  it('says a lock that has ended no longer holds', async () => {
    const ended = { ...THABO_ACCOUNT, lockedUntil: '2026-03-12T07:30:00+02:00' }
    await openUsers({ [USERS_ROUTE]: () => jsonResponse(userPage([ended])) })

    expect(within(await rowOf(ended.fullName)).getByText('Not locked')).toBeVisible()
  })

  it('draws a skeleton while it loads', async () => {
    await openUsers({ [USERS_ROUTE]: neverAnswers })

    expect(await within(accountsRegion()).findByText('Loading the staff accounts.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(accountsRegion().querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read, and reads it again on a retry', async () => {
    const { user, network } = await openUsers({ [USERS_ROUTE]: () => problemResponse(500, { requestId: 'req-users-1' }) })

    const alert = await within(accountsRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the staff accounts')
    expect(within(alert).getByText('req-users-1')).toBeVisible()

    network.setRoute(USERS_ROUTE, () => jsonResponse(userPage([THABO_ACCOUNT])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await rowOf(THABO_ACCOUNT.fullName)).toBeVisible()
  })

  it('says so when nothing matches, and clears the filters', async () => {
    const { user, network } = await openUsers(
      { [USERS_ROUTE]: () => jsonResponse(userPage([])) },
      `${USERS}?q=nobody&role=ADMIN&active=false`,
    )

    expect(await screen.findByText('No staff account matches', {}, SCREEN_WAIT)).toBeVisible()
    expect(lastAsked(network, USERS_ROUTE).toString()).toBe('q=nobody&role=ADMIN&active=false&page=1&pageSize=20')
    await user.click(screen.getByRole('button', { name: 'Clear the filters' }))

    await waitFor(() => expect(currentAddress()).toBe(USERS))
    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).toString()).toBe('page=1&pageSize=20'))
  })

  it('offers to add the first account when there is none', async () => {
    const { user } = await openUsers({ [USERS_ROUTE]: () => jsonResponse(userPage([])) })

    expect(await screen.findByText('There are no staff accounts yet', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(within(accountsRegion()).getByRole('button', { name: 'Add a staff account' }))

    expect(await screen.findByRole('heading', { level: 3, name: 'A new staff account' }, SCREEN_WAIT)).toHaveFocus()
  })
})

describe('the search, the filters and the pages', () => {
  it('searches a moment after the last key and keeps the search in the address', async () => {
    const { user, network } = await openUsers()
    await findAccounts()

    await user.type(screen.getByLabelText('Search by name or email'), 'thabo')

    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).get('q')).toBe('thabo'), SCREEN_WAIT)
    expect(currentAddress()).toBe(`${USERS}?q=thabo`)
    expect(network.requestsTo(USERS_ROUTE).filter((request) => request.query.has('q'))).toHaveLength(1)
  })

  it('narrows to one role and to the accounts that cannot sign in, as they are chosen', async () => {
    const { user, network } = await openUsers()
    await findAccounts()

    await user.selectOptions(screen.getByLabelText('Role'), 'COUNTER_STAFF')
    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).get('role')).toBe('COUNTER_STAFF'))
    await user.selectOptions(screen.getByLabelText('Can they sign in?'), 'No, deactivated')

    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).get('active')).toBe('false'))
    expect(currentAddress()).toBe(`${USERS}?role=COUNTER_STAFF&active=false`)
  })

  it('asks for another page, keeps it in the address and moves focus to the top of the accounts', async () => {
    const { user, network } = await openUsers({ [USERS_ROUTE]: () => jsonResponse(userPage([THABO_ACCOUNT], { total: 41 })) })
    await findAccounts()

    await user.click(screen.getByRole('button', { name: 'Page 3' }))

    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).get('page')).toBe('3'))
    expect(currentAddress()).toBe(`${USERS}?page=3`)
    expect(accountsRegion()).toHaveFocus()
  })

  it('offers the first page when the page asked for is past the end', async () => {
    const { user, network } = await openUsers({ [USERS_ROUTE]: () => jsonResponse(userPage([], { total: 3, page: 9 })) }, `${USERS}?page=9`)

    await user.click(await screen.findByRole('button', { name: 'Go to the first page' }, SCREEN_WAIT))

    await waitFor(() => expect(currentAddress()).toBe(USERS))
    await waitFor(() => expect(lastAsked(network, USERS_ROUTE).get('page')).toBe('1'))
  })

  it('puts a refusal under the control it names and lists any other', async () => {
    await openUsers(
      {
        [USERS_ROUTE]: () =>
          problemResponse(422, {
            errors: { fields: { 'query.q': 'Search with two to eighty characters.', 'query.pageSize': 'Ask for 100 at most.' } },
          }),
      },
      `${USERS}?q=x`,
    )

    expect(await screen.findByText('The staff accounts cannot be read with those filters', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText('Search by name or email')).toHaveAccessibleDescription('Search with two to eighty characters.')
    expect(screen.getByText('Ask for 100 at most.')).toBeVisible()
  })
})
