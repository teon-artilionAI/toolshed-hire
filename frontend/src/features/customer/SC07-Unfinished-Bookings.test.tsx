/**
 * Tests for the bookings SC-07 leaves out, with the network replaced at
 * `fetch`.
 *
 * A basket that was priced and never held stays on the server as a booking
 * that was not finished. The list does not show those until the filter asks
 * for them. It says how many it left out, counts without them, and still has
 * something sensible to say when a page holds nothing else.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, problemResponse } from '../../test/api-mock'
import type { RouteHandler } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { currentAddress } from '../../test/render-app'
import {
  CONFIRMED,
  DRAFT,
  LIST_ROUTE,
  REFERENCE,
  SECOND_REFERENCE,
  SECOND_RESERVATION_ID,
  pageOf,
} from '../../test/reservation-samples'
import {
  COUNT_QUERY,
  countRequests,
  lastPageAsked,
  list,
  listRoute,
  openList,
  openListWith,
} from './SC07-test-kit'

const UNFINISHED = { ...DRAFT, id: SECOND_RESERVATION_ID, reference: SECOND_REFERENCE }
const ONE_LEFT_OUT = '1 booking you started and did not finish is left out of this list.'

/** A confirmed booking and an unfinished one, or only the unfinished one when
 *  the filter asks for those. */
const mixed: RouteHandler = (request) =>
  jsonResponse(
    request.query.get('status') === 'DRAFT' ? pageOf([UNFINISHED]) : pageOf([CONFIRMED, UNFINISHED]),
  )

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('bookings that were not finished', () => {
  it('are left out of the list, and the count is given without them', async () => {
    await openList(mixed, '/reservations', 1)

    expect(await screen.findByText(REFERENCE)).toBeVisible()
    expect(screen.queryByText(SECOND_REFERENCE)).not.toBeInTheDocument()
    expect(within(list()).getAllByRole('row')).toHaveLength(2)
    expect(within(list()).getAllByRole('status')[0]).toHaveTextContent('1 booking on your account.')
    expect(screen.getByText(ONE_LEFT_OUT)).toBeVisible()
  })

  it('are counted with the smallest page there is, and only when no status is chosen', async () => {
    const user = userEvent.setup()
    const network = await openList(mixed, '/reservations', 1)
    await screen.findByText(REFERENCE)

    expect(countRequests(network)).toHaveLength(1)
    expect(countRequests(network)[0].query.toString()).toBe(COUNT_QUERY)

    await user.selectOptions(screen.getByLabelText('Filter by status'), 'Confirmed')

    await waitFor(() => expect(lastPageAsked(network)).toBe('status=CONFIRMED&page=1&pageSize=20'))
    expect(countRequests(network)).toHaveLength(1)
    expect(screen.queryByText(ONE_LEFT_OUT)).not.toBeInTheDocument()
  })

  it('are shown when the person asks for them, through the status filter', async () => {
    const user = userEvent.setup()
    const network = await openList(mixed, '/reservations', 1)
    await screen.findByText(REFERENCE)

    await user.click(screen.getByRole('button', { name: /^Show it/ }))

    expect(await screen.findByText(SECOND_REFERENCE)).toBeVisible()
    expect(screen.getByLabelText('Filter by status')).toHaveDisplayValue('Not finished')
    expect(currentAddress()).toBe('/reservations?status=DRAFT')
    expect(lastPageAsked(network)).toBe('status=DRAFT&page=1&pageSize=20')
    expect(within(list()).getAllByRole('status')[0]).toHaveTextContent(
      '1 booking with the status Not finished.',
    )
    expect(screen.queryByText(ONE_LEFT_OUT)).not.toBeInTheDocument()
  })

  it('are named in the plural when there are several', async () => {
    await openList(mixed, '/reservations', 3)

    expect(
      await screen.findByText('3 bookings you started and did not finish are left out of this list.'),
    ).toBeVisible()
    expect(screen.getByRole('button', { name: /^Show them/ })).toBeVisible()
  })

  it('leave a customer who has made nothing else with "no bookings yet"', async () => {
    await openList(() => jsonResponse(pageOf([UNFINISHED])), '/reservations', 1)

    expect(await screen.findByText('You have no bookings yet')).toBeVisible()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(within(list()).getAllByRole('status')[0]).toHaveTextContent('0 bookings on your account.')
    expect(screen.getByText(ONE_LEFT_OUT)).toBeVisible()
  })

  it('say so when they fill a page, and keep the way to the other pages', async () => {
    await openList(() => jsonResponse(pageOf([UNFINISHED], { total: 45 })), '/reservations', 3)

    expect(await screen.findByText('Nothing on this page was finished')).toBeVisible()
    expect(within(list()).getAllByRole('status')[0]).toHaveTextContent('42 bookings on your account.')
    expect(
      within(screen.getByRole('navigation', { name: 'Booking pages' })).getByRole('status'),
    ).toHaveTextContent('Page 1 of 3')
  })

  it('fail the list when they cannot be counted, and load on a retry', async () => {
    const user = userEvent.setup()
    const network = await openListWith((request) =>
      request.query.has('status')
        ? problemResponse(500, { requestId: 'req-count-7' })
        : jsonResponse(pageOf([CONFIRMED])),
    )

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load your bookings')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()

    network.setRoute(LIST_ROUTE, listRoute(() => jsonResponse(pageOf([CONFIRMED]))))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(REFERENCE)).toBeVisible()
  })
})
