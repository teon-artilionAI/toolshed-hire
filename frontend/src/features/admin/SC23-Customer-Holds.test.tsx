/**
 * Tests for the customer holds on SC-23, with the network replaced at `fetch`.
 *
 * The holds are one paged read filtered by standing and searched by name,
 * phone or email. Waiting, failed, empty and loaded, the two views as links,
 * the moves each customer offers, each asking why and saying what it does to
 * the customer's bookings, releasing a hold saying the count of bookings not
 * collected is kept, the body of every move, a 409, a 403 and a 422, the
 * answer disabled in flight, the list read again, and paging.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CustomerSummary } from '../../shared/api/contract'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { BLACKLISTED, CUSTOMER_HOLDS_ROUTE, holdPage, standingRoute } from '../../test/admin-user-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { ON_HOLD, THANDI } from '../../test/counter-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { HOLDS, USERS, findCustomer, lastAsked, lastBody, openUsers } from './SC23-test-kit'

const REASON = 'Paid the outstanding late fees in full.'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function customersRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'The customers' })
}

function movesOf(entry: HTMLElement): string[] {
  return within(within(entry).getByRole('list')).getAllByRole('button').map((button) => button.textContent ?? '')
}

describe('the two views', () => {
  it('opens the customer holds on the customers who are on hold, from a link, and moves focus to its heading', async () => {
    const { user, network } = await openUsers()

    await user.click(screen.getByRole('link', { name: 'Customer holds' }))

    expect(await screen.findByRole('heading', { level: 2, name: 'Customer holds' }, SCREEN_WAIT)).toHaveFocus()
    expect(currentAddress()).toBe(HOLDS)
    expect(screen.getByRole('link', { name: 'Customer holds' })).toHaveAttribute('aria-current', 'page')
    await waitFor(() => expect(lastAsked(network, CUSTOMER_HOLDS_ROUTE).toString()).toBe('status=ON_HOLD&page=1&pageSize=20'))
    expect(screen.getByLabelText('Standing')).toHaveDisplayValue('Account on hold')
  })

  it('goes back to the staff accounts from a link', async () => {
    const { user } = await openUsers({}, HOLDS)

    await user.click(screen.getByRole('link', { name: 'Staff accounts' }))

    expect(await screen.findByRole('heading', { level: 2, name: 'Staff accounts' }, SCREEN_WAIT)).toHaveFocus()
    expect(currentAddress()).toBe(USERS)
  })
})

describe('reading the customer holds', () => {
  it('shows each customer as the server sent them, in words', async () => {
    await openUsers({}, HOLDS)

    const held = await findCustomer(ON_HOLD.displayName)
    expect(within(customersRegion()).getByText('3 customers, account on hold.')).toBeVisible()
    expect(within(held).getByText('Account on hold', { selector: '.pill' })).toBeVisible()
    expect(within(held).getByText('3 bookings')).toBeVisible()
    expect(within(held).getByText('No online account')).toBeVisible()
    expect(within(held).getByText('Bellville')).toBeVisible()

    const blacklisted = await findCustomer(BLACKLISTED.displayName)
    expect(within(blacklisted).getByText('VW Construct')).toBeVisible()
    expect(within(blacklisted).getByText('Blacklisted', { selector: '.pill' })).toBeVisible()
  })

  it('offers the two standings each customer is not in', async () => {
    await openUsers({}, HOLDS)

    expect(movesOf(await findCustomer(ON_HOLD.displayName))).toEqual([
      `Release the hold for ${ON_HOLD.displayName}`,
      `Blacklist for ${ON_HOLD.displayName}`,
    ])
    expect(movesOf(await findCustomer(THANDI.displayName))).toEqual([
      `Put on hold for ${THANDI.displayName}`,
      `Blacklist for ${THANDI.displayName}`,
    ])
    expect(movesOf(await findCustomer(BLACKLISTED.displayName))).toEqual([
      `Lift the blacklisting for ${BLACKLISTED.displayName}`,
      `Put on hold for ${BLACKLISTED.displayName}`,
    ])
  })

  it('draws a skeleton while it loads', async () => {
    await openUsers({ [CUSTOMER_HOLDS_ROUTE]: neverAnswers }, HOLDS)

    expect(await within(customersRegion()).findByText('Loading the customers.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(customersRegion().querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read', async () => {
    await openUsers({ [CUSTOMER_HOLDS_ROUTE]: () => problemResponse(500, { requestId: 'req-holds-1' }) }, HOLDS)

    const alert = await within(customersRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the customers')
    expect(within(alert).getByText('req-holds-1')).toBeVisible()
  })

  it('says nobody is on hold, and shows every customer on request', async () => {
    const { user, network } = await openUsers({ [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage([])) }, HOLDS)

    expect(await screen.findByText('Nobody is on hold, so every customer may book.', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Show every customer' }))

    await waitFor(() => expect(currentAddress()).toBe(`${USERS}?view=customers`))
    await waitFor(() => expect(lastAsked(network, CUSTOMER_HOLDS_ROUTE).toString()).toBe('page=1&pageSize=20'))
  })

  it('narrows by standing and searches a moment after the last key, in the address', async () => {
    const { user, network } = await openUsers({}, HOLDS)
    await findCustomer(ON_HOLD.displayName)

    await user.selectOptions(screen.getByLabelText('Standing'), 'Blacklisted')
    await waitFor(() => expect(lastAsked(network, CUSTOMER_HOLDS_ROUTE).get('status')).toBe('BLACKLISTED'))
    await user.type(screen.getByLabelText('Search by name, phone or email'), 'riaan')

    await waitFor(() => expect(lastAsked(network, CUSTOMER_HOLDS_ROUTE).get('q')).toBe('riaan'), SCREEN_WAIT)
    expect(currentAddress()).toBe(`${USERS}?view=customers&status=BLACKLISTED&q=riaan`)
  })

  it('asks for another page and moves focus to the top of the customers', async () => {
    const { user, network } = await openUsers({ [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage([ON_HOLD], { total: 45 })) }, HOLDS)
    await findCustomer(ON_HOLD.displayName)

    await user.click(screen.getByRole('button', { name: 'Page 2' }))

    await waitFor(() => expect(lastAsked(network, CUSTOMER_HOLDS_ROUTE).get('page')).toBe('2'))
    expect(currentAddress()).toBe(`${HOLDS}&page=2`)
    expect(customersRegion()).toHaveFocus()
  })

  it('puts a refused search under its box', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'query.q': 'Search with two to eighty characters.' } } })
    await openUsers({ [CUSTOMER_HOLDS_ROUTE]: refusal }, `${HOLDS}&q=x`)

    expect(await screen.findByText('The customers cannot be read with those filters', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText('Search by name, phone or email')).toHaveAccessibleDescription('Search with two to eighty characters.')
  })
})

describe('moving a customer', () => {
  const released: CustomerSummary = { ...ON_HOLD, accountStatus: 'ACTIVE' }

  it('releases a hold after asking why, says the count of bookings not collected is kept, and reads the list again', async () => {
    const { user, network } = await openUsers({ [standingRoute(ON_HOLD.id)]: () => jsonResponse(released) }, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    const listReads = network.requestsTo(CUSTOMER_HOLDS_ROUTE).length
    await user.click(within(entry).getByRole('button', { name: /^Release the hold/ }))

    expect(screen.getByRole('heading', { level: 4, name: `Release the hold on ${ON_HOLD.displayName}?` })).toHaveFocus()
    expect(within(entry).getByText(/can make new bookings again from now\. Their count of bookings not collected stays at 3, because releasing a hold does not reset it\./)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, release the hold' }))
    expect(within(entry).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('Write the reason'))
    expect(network.requestsTo(standingRoute(ON_HOLD.id))).toHaveLength(0)

    await user.type(within(entry).getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, release the hold' }))

    const outcome = await screen.findByText(`${ON_HOLD.displayName} is in good standing again`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(screen.getByText(/They can make new bookings again\. Their count of bookings not collected stays at 3/)).toBeVisible()
    expect(lastBody(network, standingRoute(ON_HOLD.id))).toEqual({ accountStatus: 'ACTIVE', reason: REASON })
    await waitFor(() => expect(network.requestsTo(CUSTOMER_HOLDS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('puts a customer on hold, saying their confirmed bookings stay as they are', async () => {
    const held = { ...THANDI, accountStatus: 'ON_HOLD' as const }
    const { user, network } = await openUsers({ [standingRoute(THANDI.id)]: () => jsonResponse(held) }, HOLDS)
    const entry = await findCustomer(THANDI.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Put on hold/ }))

    expect(within(entry).getByText(/cannot make a new booking until the hold is released\. Bookings already confirmed stay as they are/)).toBeVisible()
    await user.type(within(entry).getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, put on hold' }))

    expect(await screen.findByText(`${THANDI.displayName} is on hold`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, standingRoute(THANDI.id))).toEqual({ accountStatus: 'ON_HOLD', reason: REASON })
  })

  it('blacklists a customer, saying what that does to their bookings', async () => {
    const { user, network } = await openUsers({ [standingRoute(ON_HOLD.id)]: () => jsonResponse({ ...ON_HOLD, accountStatus: 'BLACKLISTED' }) }, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Blacklist/ }))

    expect(within(entry).getByText(/cannot make a new booking at any branch until the blacklisting is lifted/)).toBeVisible()
    await user.type(within(entry).getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, blacklist' }))

    expect(await screen.findByText(`${ON_HOLD.displayName} is blacklisted`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, standingRoute(ON_HOLD.id))).toEqual({ accountStatus: 'BLACKLISTED', reason: REASON })
  })

  it.each([
    [409, 'Sipho Ndlovu was moved by another administrator a moment ago. Read the list again.'],
    [403, 'Only an administrator may change the standing of a customer.'],
  ])('shows the sentence of a %i', async (status, detail) => {
    const { user } = await openUsers({ [standingRoute(ON_HOLD.id)]: () => problemResponse(status, { detail }) }, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Release the hold/ }))
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release the hold' }))

    const alert = await within(entry).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`The standing of ${ON_HOLD.displayName} was not changed`)
    expect(alert).toHaveTextContent(detail)
  })

  it('puts a refused reason under its box', async () => {
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.reason': 'Give a reason of 5 to 200 characters.' } } })
    const { user } = await openUsers({ [standingRoute(ON_HOLD.id)]: refusal }, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Release the hold/ }))
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release the hold' }))

    await waitFor(() =>
      expect(within(entry).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('5 to 200 characters')),
    )
    expect(within(entry).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openUsers({ [standingRoute(ON_HOLD.id)]: neverAnswers }, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Release the hold/ }))
    await user.type(within(entry).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release the hold' }))

    const waiting = await screen.findByRole('button', { name: 'Releasing the hold' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(standingRoute(ON_HOLD.id))).toHaveLength(1)
  })

  it('puts the question away unanswered and gives focus back to its button', async () => {
    const { user, network } = await openUsers({}, HOLDS)
    const entry = await findCustomer(ON_HOLD.displayName)
    await user.click(within(entry).getByRole('button', { name: /^Blacklist/ }))

    await user.click(within(entry).getByRole('button', { name: 'Leave it as it is' }))

    await waitFor(() => expect(within(entry).getByRole('button', { name: /^Blacklist/ })).toHaveFocus())
    expect(network.requestsTo(standingRoute(ON_HOLD.id))).toHaveLength(0)
  })
})
