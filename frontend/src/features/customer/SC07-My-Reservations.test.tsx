/**
 * Tests for SC-07 My Reservations, with the network replaced at `fetch`.
 *
 * The list is the server's. Each test sets what the list route answers, opens
 * the screen as the signed in customer, and reads it the way a person would.
 * Loading, failed, empty and loaded, then the filter and the paging, which
 * both live in the address.
 *
 * With no status chosen the screen asks the list route twice. Once for the
 * page, and once for how many bookings were started and not finished, which it
 * leaves out. `listRoute` answers the second question for a test, so the test
 * only has to say what the page holds. SC07-Unfinished-Bookings.test.tsx is
 * about the ones that are left out.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { currentAddress } from '../../test/render-app'
import {
  CANCELLED,
  CONFIRMED,
  HELD,
  LIST_ROUTE,
  REFERENCE,
  SECOND_REFERENCE,
  SECOND_RESERVATION_ID,
  pageOf,
} from '../../test/reservation-samples'
import { CUSTOMER } from '../../test/session-samples'
import { lastPageAsked, list, listRoute, openList } from './SC07-test-kit'

const HELD_SECOND = { ...HELD, id: SECOND_RESERVATION_ID, reference: SECOND_REFERENCE }

/** The row of one booking, found by its reference. */
function rowOf(reference: string): HTMLElement {
  const row = screen.getByText(reference).closest('tr')
  if (!row) throw new Error(`No row shows ${reference}.`)
  return row
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the list is loading', () => {
  it('says so in a polite status and shows no row', async () => {
    await openList(neverAnswers)

    expect(within(list()).getByRole('status')).toHaveTextContent('Loading your bookings.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(list().querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})

describe('when the list fails to load', () => {
  it('says so in plain words with the reference, and loads on a retry', async () => {
    const user = userEvent.setup()
    const network = await openList(() => problemResponse(500, { requestId: 'req-list-4' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load your bookings')
    expect(within(alert).getByText('req-list-4')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')
    expect(within(list()).getByRole('status')).toHaveTextContent('Your bookings did not load.')

    network.setRoute(LIST_ROUTE, listRoute(() => jsonResponse(pageOf([CONFIRMED]))))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(REFERENCE)).toBeVisible()
  })
})

describe('when the customer has no bookings', () => {
  it('says so and points to the catalogue', async () => {
    await openList(() => jsonResponse(pageOf([])))

    expect(await screen.findByText('You have no bookings yet')).toBeVisible()
    expect(within(list()).getByRole('link', { name: 'Browse the catalogue' })).toHaveAttribute('href', '/')
    expect(within(list()).getByRole('status')).toHaveTextContent('0 bookings on your account.')
  })
})

describe('the loaded list', () => {
  it('asks for the first page of twenty, with no status', async () => {
    const network = await openList(() => jsonResponse(pageOf([CONFIRMED])))
    await screen.findByText(REFERENCE)

    expect(lastPageAsked(network)).toBe('page=1&pageSize=20')
  })

  it('shows each booking with its reference, branch, dates, status and total, linked to its detail', async () => {
    await openList(() => jsonResponse(pageOf([CONFIRMED, HELD_SECOND])))

    const confirmed = within(await waitFor(() => rowOf(REFERENCE)))
    expect(confirmed.getByText('2 x CP 100 Plate Compactor')).toBeVisible()
    expect(confirmed.getByText('12 Mar to 16 Mar 2026')).toBeVisible()
    expect(confirmed.getByText('4 days')).toBeVisible()
    expect(confirmed.getByText('Cape Town CBD')).toBeVisible()
    expect(confirmed.getByText('Confirmed')).toBeVisible()
    // The total is the one the server sent, which no sum on the row could reach.
    expect(confirmed.getByText(/^R 4.444[,.]44$/)).toBeVisible()
    expect(confirmed.getByRole('link', { name: `View booking ${REFERENCE}` })).toHaveAttribute(
      'href',
      `/reservations/${REFERENCE}`,
    )

    const held = within(rowOf(SECOND_REFERENCE))
    expect(held.getByText('Held for you')).toBeVisible()
    expect(held.getByText('Until 08:30')).toBeVisible()
    expect(within(list()).getByRole('status')).toHaveTextContent('2 bookings on your account.')
    expect(screen.getByText(`Every booking on the account for ${CUSTOMER.fullName}, newest first.`)).toBeVisible()
    expect(screen.queryByText(/left out of this list/)).not.toBeInTheDocument()
  })

  it('keeps the order the server sent', async () => {
    await openList(() => jsonResponse(pageOf([HELD_SECOND, CONFIRMED])))
    await screen.findByText(REFERENCE)

    const references = within(list())
      .getAllByRole('row')
      .slice(1)
      .map((row) => row.querySelector('p')?.textContent)
    expect(references).toEqual([SECOND_REFERENCE, REFERENCE])
  })
})

describe('the status filter', () => {
  it('asks the server for one status, from the first page, and puts it in the address', async () => {
    const user = userEvent.setup()
    const network = await openList(
      (request) =>
        jsonResponse(request.query.get('status') === 'CANCELLED' ? pageOf([CANCELLED]) : pageOf([CONFIRMED])),
      '/reservations?page=3',
    )
    await screen.findByText('Confirmed', { selector: 'span' })

    await user.selectOptions(screen.getByLabelText('Filter by status'), 'Cancelled')

    await waitFor(() => expect(lastPageAsked(network)).toBe('status=CANCELLED&page=1&pageSize=20'))
    expect(currentAddress()).toBe('/reservations?status=CANCELLED')
    await waitFor(() =>
      expect(within(list()).getByRole('status')).toHaveTextContent('1 booking with the status Cancelled.'),
    )
  })

  it('offers every status the API has, by the name a customer reads', async () => {
    await openList(() => jsonResponse(pageOf([CONFIRMED])))

    const options = within(screen.getByLabelText('Filter by status')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual([
      'All bookings',
      'Not finished',
      'Held for you',
      'Confirmed',
      'Out with you',
      'Returned',
      'Cancelled',
      'Not collected',
      'Expired',
    ])
  })

  it('says so when nothing has that status, and clears the filter on request', async () => {
    const user = userEvent.setup()
    const network = await openList(
      (request) => jsonResponse(request.query.has('status') ? pageOf([]) : pageOf([CONFIRMED])),
      '/reservations?status=NO_SHOW',
    )

    expect(await screen.findByText('No bookings have that status')).toBeVisible()
    expect(screen.getByLabelText('Filter by status')).toHaveDisplayValue('Not collected')

    await user.click(screen.getByRole('button', { name: 'Clear the filter' }))

    expect(await screen.findByText(REFERENCE)).toBeVisible()
    expect(currentAddress()).toBe('/reservations')
    expect(lastPageAsked(network)).toBe('page=1&pageSize=20')
  })

  it.each([
    ['/reservations?status=BANANA&page=-2', 'page=1&pageSize=20'],
    ['/reservations?status=held&page=two', 'page=1&pageSize=20'],
    ['/reservations?status=HELD&page=4', 'status=HELD&page=4&pageSize=20'],
  ])('reads %s from the address, and falls back for what it cannot offer', async (at, asked) => {
    const network = await openList(() => jsonResponse(pageOf([CONFIRMED])), at)
    await screen.findByText(REFERENCE)

    expect(lastPageAsked(network)).toBe(asked)
  })
})

describe('paging', () => {
  const pages: RouteHandler = (request) => {
    const page = Number(request.query.get('page'))
    return jsonResponse(pageOf([page === 2 ? HELD_SECOND : CONFIRMED], { page, pageSize: 20, total: 45 }))
  }

  it('shows the page controls from what the server says, and asks for the next page', async () => {
    const user = userEvent.setup()
    const network = await openList(pages)
    await screen.findByText(REFERENCE)
    const controls = screen.getByRole('navigation', { name: 'Booking pages' })
    expect(within(controls).getByRole('status')).toHaveTextContent('Page 1 of 3')

    await user.click(within(controls).getByRole('button', { name: 'Next' }))

    expect(await screen.findByText(SECOND_REFERENCE)).toBeVisible()
    expect(lastPageAsked(network)).toBe('page=2&pageSize=20')
    expect(currentAddress()).toBe('/reservations?page=2')
    expect(list()).toHaveFocus()
    expect(
      within(screen.getByRole('navigation', { name: 'Booking pages' })).getByRole('status'),
    ).toHaveTextContent('Page 2 of 3')
  })

  it('keeps the filter when the page changes', async () => {
    const user = userEvent.setup()
    const network = await openList(pages, '/reservations?status=CONFIRMED')
    await screen.findByText(REFERENCE)

    await user.click(screen.getByRole('button', { name: 'Page 2' }))

    await waitFor(() => expect(lastPageAsked(network)).toBe('status=CONFIRMED&page=2&pageSize=20'))
    expect(currentAddress()).toBe('/reservations?status=CONFIRMED&page=2')
  })

  it('has no page controls when everything fits on one page', async () => {
    await openList(() => jsonResponse(pageOf([CONFIRMED])))
    await screen.findByText(REFERENCE)

    expect(screen.queryByRole('navigation', { name: 'Booking pages' })).not.toBeInTheDocument()
  })

  it('offers the first page when the address asks for one past the end', async () => {
    const user = userEvent.setup()
    await openList(
      (request) =>
        jsonResponse(
          request.query.get('page') === '9'
            ? pageOf([], { page: 9, total: 1 })
            : pageOf([CONFIRMED]),
        ),
      '/reservations?page=9',
    )

    expect(await screen.findByText('That page is past the end of your bookings')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Go to the first page' }))

    expect(await screen.findByText(REFERENCE)).toBeVisible()
    expect(currentAddress()).toBe('/reservations')
  })
})
