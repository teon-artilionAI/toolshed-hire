/**
 * Tests for the search on SC-12 Customer Lookup, with the network replaced at
 * `fetch`.
 *
 * The list is the server's. Each test says how the customer route answers,
 * types into the one search box the way an assistant would, and reads the
 * page. Waiting, failed, nothing found and found, then the paging, then the
 * customer chosen with their bookings. The walk in form is in
 * SC12-Walkin-Form.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  COUNTER_CONFIRMED,
  CUSTOMERS_ROUTE,
  CUSTOMER_ID,
  ON_HOLD,
  THANDI,
  WESLEY,
  customerPage,
  customerRoute,
} from '../../test/counter-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { LIST_ROUTE, REFERENCE, SECOND_REFERENCE, pageOf } from '../../test/reservation-samples'
import { CHOSEN_READS, SEARCH_BOX, openLookup } from './SC12-test-kit'

function results(): HTMLElement {
  return screen.getByRole('region', { name: 'Customers found' })
}

function lastSearch(requests: { query: URLSearchParams }[]): string {
  return requests[requests.length - 1].query.toString()
}

/** The block of one customer in the results, found by their name. */
async function rowOf(name: string): Promise<HTMLElement> {
  const row = (await within(results()).findByText(name, {}, SCREEN_WAIT)).closest('li')
  if (!row) throw new Error(`No block in the results shows ${name}.`)
  return row
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('before anything is typed', () => {
  it('is connected, asks for two characters, and searches for nothing', async () => {
    const { user, network } = await openLookup({ [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([THANDI])) })

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(within(results()).getByRole('status')).toHaveTextContent('Type 2 characters or more to search.')

    await user.type(screen.getByLabelText(SEARCH_BOX), 't')

    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(network.requestsTo(CUSTOMERS_ROUTE)).toHaveLength(0)
  })
})

describe('while the search runs', () => {
  it('says so in a polite status and draws a skeleton', async () => {
    const { user } = await openLookup({ [CUSTOMERS_ROUTE]: neverAnswers })

    await user.type(screen.getByLabelText(SEARCH_BOX), 'thandi')

    await waitFor(() => expect(within(results()).getByRole('status')).toHaveTextContent('Searching for customers.'))
    expect(results().querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})

describe('when the search fails', () => {
  it('says so in plain words with the reference, and searches on a retry', async () => {
    const { user, network } = await openLookup({
      [CUSTOMERS_ROUTE]: () => problemResponse(500, { requestId: 'req-customers-1' }),
    })
    await user.type(screen.getByLabelText(SEARCH_BOX), 'thandi')

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the customers')
    expect(within(alert).getByText('req-customers-1')).toBeVisible()

    network.setRoute(CUSTOMERS_ROUTE, () => jsonResponse(customerPage([THANDI])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await within(results()).findByText(THANDI.displayName)).toBeVisible()
  })
})

describe('when nobody matches', () => {
  it('says so and takes the assistant to the walk in form', async () => {
    const { user } = await openLookup({ [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([])) })
    await user.type(screen.getByLabelText(SEARCH_BOX), 'nobody here')

    expect(await screen.findByText('Nobody on file matches that', {}, SCREEN_WAIT)).toBeVisible()
    expect(within(results()).getByRole('status')).toHaveTextContent('Nobody on file matches "nobody here".')

    await user.click(within(results()).getByRole('button', { name: 'Register a walk in' }))

    expect(screen.getByLabelText('Full name')).toHaveFocus()
  })
})

describe('the customers found', () => {
  it('asks the server with the search, the first page and its size, and keeps the search in the address', async () => {
    const { user, network } = await openLookup({ [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([THANDI])) })

    await user.type(screen.getByLabelText(SEARCH_BOX), ' 082 441 ')

    await within(results()).findByText(THANDI.displayName, {}, SCREEN_WAIT)
    expect(lastSearch(network.requestsTo(CUSTOMERS_ROUTE))).toBe('q=082+441&page=1&pageSize=10')
    expect(currentAddress()).toBe('/counter/customers?q=082+441')
  })

  it('shows who each one is, how the account stands, whether there is a login, and offers a booking', async () => {
    await openLookup(
      { [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([THANDI, WESLEY])) },
      undefined,
      '/counter/customers?q=thandi',
    )

    const thandi = within(await rowOf(THANDI.displayName))
    expect(thandi.getByText(THANDI.displayName)).toBeVisible()
    expect(thandi.getByText('0824417719')).toBeVisible()
    expect(thandi.getByText('No email on file')).toBeVisible()
    expect(thandi.getByText('Good standing')).toBeVisible()
    expect(thandi.getByText('No login')).toBeVisible()
    expect(thandi.getByText(/South African ID ending 5083/)).toBeVisible()
    expect(thandi.getByRole('link', { name: `New booking for ${THANDI.displayName}` })).toHaveAttribute(
      'href',
      `/counter/booking?customer=${CUSTOMER_ID}`,
    )
    expect(within(results()).getByText('Has a login')).toBeVisible()
    expect(within(results()).getByText('BuildRight Construction')).toBeVisible()
    expect(within(results()).getByRole('status')).toHaveTextContent('2 customers match "thandi". The best match is first.')
  })

  it('says an account on hold is on hold and offers it no booking', async () => {
    await openLookup(
      { [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([ON_HOLD])) },
      undefined,
      '/counter/customers?q=sipho',
    )

    expect(await within(results()).findByText('Account on hold', {}, SCREEN_WAIT)).toBeVisible()
    expect(within(results()).getByText(/no new booking can be made until an administrator lifts the hold/)).toBeVisible()
    expect(within(results()).queryByRole('link', { name: /New booking/ })).not.toBeInTheDocument()
  })
})

describe('paging', () => {
  const pages: RouteHandler = (request) => {
    const page = Number(request.query.get('page'))
    return jsonResponse(customerPage([page === 2 ? WESLEY : THANDI], { page, total: 25 }))
  }

  it('shows the page controls from what the server says, and asks for the next page', async () => {
    const { user, network } = await openLookup({ [CUSTOMERS_ROUTE]: pages }, undefined, '/counter/customers?q=th')
    await within(results()).findByText(THANDI.displayName, {}, SCREEN_WAIT)
    const controls = screen.getByRole('navigation', { name: 'Customer result pages' })
    expect(within(controls).getByRole('status')).toHaveTextContent('Page 1 of 3')

    await user.click(within(controls).getByRole('button', { name: 'Next' }))

    expect(await within(results()).findByText(WESLEY.displayName)).toBeVisible()
    expect(lastSearch(network.requestsTo(CUSTOMERS_ROUTE))).toBe('q=th&page=2&pageSize=10')
    expect(currentAddress()).toBe('/counter/customers?q=th&page=2')
    expect(results()).toHaveFocus()
  })
})

describe('choosing a customer', () => {
  it('shows them with their bookings, and offers the checkout only for one due here today', async () => {
    const elsewhere = { ...COUNTER_CONFIRMED, id: 'r-2', reference: SECOND_REFERENCE, branchCode: 'CBD', branchName: 'Cape Town CBD' }
    const later = { ...COUNTER_CONFIRMED, id: 'r-3', reference: 'TSH-R-26-000126', from: '2026-03-20', to: '2026-03-21' }
    const { user, network } = await openLookup(
      {
        [CUSTOMERS_ROUTE]: () => jsonResponse(customerPage([THANDI])),
        ...CHOSEN_READS,
        [LIST_ROUTE]: () => jsonResponse(pageOf([COUNTER_CONFIRMED, elsewhere, later])),
      },
      undefined,
      '/counter/customers?q=thandi',
    )

    await user.click(await screen.findByRole('button', { name: `Show bookings for ${THANDI.displayName}` }, SCREEN_WAIT))

    expect(await screen.findByRole('heading', { level: 2, name: THANDI.displayName }, SCREEN_WAIT)).toHaveFocus()
    expect(currentAddress()).toBe(`/counter/customers?q=thandi&customer=${CUSTOMER_ID}`)
    const bookings = screen.getByRole('region', { name: `Bookings for ${THANDI.displayName}` })
    expect(await within(bookings).findByText(REFERENCE, { selector: '.font-mono' })).toBeVisible()
    expect(network.requestsTo(LIST_ROUTE)[0].query.get('customerProfileId')).toBe(CUSTOMER_ID)
    expect(within(bookings).getByRole('link', { name: `Check out ${REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/checkout/${REFERENCE}`,
    )
    expect(within(bookings).getAllByRole('link')).toHaveLength(1)
    expect(within(bookings).getByText('Collected at Cape Town CBD, not at this counter.')).toBeVisible()
  })

  it('keeps the customer from the address on a reload, without taking focus', async () => {
    await openLookup(CHOSEN_READS, undefined, `/counter/customers?customer=${CUSTOMER_ID}`)

    const heading = await screen.findByRole('heading', { level: 2, name: THANDI.displayName }, SCREEN_WAIT)
    expect(heading).not.toHaveFocus()
    expect(screen.getByRole('link', { name: `New booking for ${THANDI.displayName}` })).toBeVisible()
    expect(await screen.findByText('No bookings yet.')).toBeVisible()
  })

  it('says so when the customer in the address is not on file', async () => {
    await openLookup(
      { [customerRoute()]: () => problemResponse(404, { detail: 'No such customer.' }) },
      undefined,
      `/counter/customers?customer=${CUSTOMER_ID}`,
    )

    expect(await screen.findByText('We cannot find that customer', {}, SCREEN_WAIT)).toBeVisible()
  })
})
