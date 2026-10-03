/**
 * Tests for SC-13, a booking at the counter, step by step, with the network
 * replaced at `fetch`.
 *
 * The assistant picks the tools from the availability search for their own
 * branch, and the booking goes through the same three requests as an online
 * one. Each step is one request, each button is disabled while its request is
 * in flight, and every figure on the page is the server's. The failures are in
 * SC13-Booking-Failures.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { PLATE_COMPACTOR, TEST_NOW, TEST_TODAY } from '../../test/catalogue-samples'
import {
  AVAILABILITY_ROUTE,
  COUNTER_BOOKING_WORKS,
  CUSTOMER_ID,
  DAY_AFTER_TODAY,
  ON_HOLD,
  customerRoute,
  modelAvailabilityRoute,
} from '../../test/counter-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { CREATE_ROUTE, REFERENCE, RESERVATION_ID, confirmRoute, holdRoute } from '../../test/reservation-samples'
import {
  CONFIRM,
  CONFIRMED_STEP,
  HELD_STEP,
  HOLD,
  LINES_STEP,
  PRICE,
  REVIEW_STEP,
  addTwoCompactors,
  figure,
  openBooking,
  priceTwoCompactors,
  stepHeading,
} from './SC13-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('before the booking starts', () => {
  it('asks for the customer first when the address names none', async () => {
    await openBooking({}, '/counter/booking')

    expect(screen.getByText('Find the customer first')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Find a customer' })).toHaveAttribute('href', '/counter/customers')
  })

  it('says why a customer on hold cannot be booked for, and offers no booking', async () => {
    await openBooking({ [customerRoute(ON_HOLD.id)]: () => jsonResponse(ON_HOLD) }, `/counter/booking?customer=${ON_HOLD.id}`)

    expect(await screen.findByText('No booking can be made', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(/no new booking can be made until an administrator lifts the hold/)).toBeVisible()
    expect(screen.queryByRole('button', { name: PRICE })).not.toBeInTheDocument()
  })

  it('says so when the customer in the address is not on file', async () => {
    await openBooking({ [customerRoute()]: () => problemResponse(404, { detail: 'No such customer.' }) })

    expect(await screen.findByText('We cannot find that customer', {}, SCREEN_WAIT)).toBeVisible()
  })
})

describe('choosing the dates and the tools', () => {
  it('is connected, names the customer, and starts today at the assistant branch', async () => {
    const { network } = await openBooking(COUNTER_BOOKING_WORKS)

    expect(await screen.findByText(/Booking for/, {}, SCREEN_WAIT)).toHaveTextContent('Booking for Thandi Mokoena')
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Goes out on')).toHaveValue(TEST_TODAY)
    expect(screen.getByLabelText('Comes back on')).toHaveValue(DAY_AFTER_TODAY)
    expect(screen.getByText(/Collected from Bellville/)).toBeVisible()
    await waitFor(() => expect(network.requestsTo(AVAILABILITY_ROUTE)).not.toHaveLength(0))
    expect(network.requestsTo(AVAILABILITY_ROUTE)[0].query.toString()).toBe(
      `from=${TEST_TODAY}&to=${DAY_AFTER_TODAY}&branch=BLV&page=1&pageSize=6`,
    )
  })

  it('lists what is free at the branch, and says whether each line is free for its quantity', async () => {
    const { user, network } = await openBooking(COUNTER_BOOKING_WORKS)
    const finder = await screen.findByRole('region', { name: 'Tools free at this branch' }, SCREEN_WAIT)
    await waitFor(() =>
      expect(within(finder).getByRole('status')).toHaveTextContent('2 models are free at Bellville for these dates.'),
    )
    expect(within(finder).getAllByText('Free at Bellville')).toHaveLength(2)

    await addTwoCompactors(user)

    expect(await screen.findByText('2 units free at Bellville for these dates')).toBeVisible()
    const asked = network.requestsTo(modelAvailabilityRoute())
    expect(asked[asked.length - 1].query.get('quantity')).toBe('2')
    expect(within(finder).getByRole('button', { name: `On the booking ${PLATE_COMPACTOR.name}` })).toBeDisabled()
  })

  it('offers no way to pick a unit by hand', async () => {
    const { user } = await openBooking(COUNTER_BOOKING_WORKS)
    await addTwoCompactors(user)

    expect(screen.queryByText(/Choose the unit/)).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
  })

  it('holds back a booking with no tools, and says so under the list', async () => {
    const { user, network } = await openBooking(COUNTER_BOOKING_WORKS)
    await screen.findByText(/Booking for/, {}, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: PRICE }))

    expect(screen.getByText('Add at least one tool to the booking.')).toBeVisible()
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(0)
  })
})

describe('a booking that works', () => {
  it('prices, holds and confirms, one request each, showing the server figures and the units', async () => {
    const { user, network } = await openBooking(COUNTER_BOOKING_WORKS)
    expect(await stepHeading(LINES_STEP)).toBeVisible()

    await addTwoCompactors(user)
    await user.click(screen.getByRole('button', { name: PRICE }))

    expect(await stepHeading(REVIEW_STEP)).toHaveFocus()
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(CREATE_ROUTE)[0].body).toEqual({
      branchCode: 'BLV',
      from: TEST_TODAY,
      to: DAY_AFTER_TODAY,
      lines: [{ modelSlug: PLATE_COMPACTOR.slug, quantity: 2 }],
      customerProfileId: CUSTOMER_ID,
      notes: null,
    })
    // Figures no sum on the page could reach, so they can only be the server's.
    expect(figure('Total with VAT')).toHaveTextContent(/^R 4.444[,.]44$/)
    expect(figure('Deposit to take at collection')).toHaveTextContent(/^R 5.555[,.]55$/)
    expect(screen.getByText('The booking has been priced. Nothing is held yet.')).toHaveAttribute('role', 'status')

    await user.click(screen.getByRole('button', { name: HOLD }))

    expect(await stepHeading(HELD_STEP)).toHaveFocus()
    expect(network.requestsTo(holdRoute())).toHaveLength(1)
    expect(screen.getByText('TSH-PC-0007, TSH-PC-0011')).toBeVisible()
    expect(screen.getByText(/The units are held until 08:30\. Confirm before then/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    expect(await stepHeading(CONFIRMED_STEP)).toHaveFocus()
    expect(network.requestsTo(confirmRoute())).toHaveLength(1)
    expect(screen.getByText(`Booking ${REFERENCE} is confirmed`)).toBeVisible()
    expect(screen.getByText(/Take a deposit of R 5.555[,.]55 at collection/)).toBeVisible()
    expect(screen.getByText(`The booking is confirmed. The reference is ${REFERENCE}.`)).toHaveAttribute('role', 'status')
    expect(screen.getByRole('link', { name: 'Check out now' })).toHaveAttribute('href', `/counter/checkout/${REFERENCE}`)
    expect(currentAddress()).toBe(`/counter/booking?customer=${CUSTOMER_ID}`)
  })

  it('starts another booking for the same customer from nothing', async () => {
    const { user } = await openBooking(COUNTER_BOOKING_WORKS)
    await priceTwoCompactors(user)
    await user.click(screen.getByRole('button', { name: HOLD }))
    await user.click(await screen.findByRole('button', { name: CONFIRM }, SCREEN_WAIT))
    await stepHeading(CONFIRMED_STEP)

    await user.click(screen.getByRole('button', { name: 'Another booking for Thandi Mokoena' }))

    expect(await stepHeading(LINES_STEP)).toHaveFocus()
    expect(screen.getByText('No tools yet. Find one below and add it.')).toBeVisible()
  })
})

describe('a request in flight', () => {
  it('disables the button, so the booking cannot be priced twice', async () => {
    const { user, network } = await openBooking({ ...COUNTER_BOOKING_WORKS, [CREATE_ROUTE]: neverAnswers })
    await addTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: PRICE }))

    const waiting = await screen.findByRole('button', { name: 'Working out the cost' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
  })

  it('disables the hold and the way back while the hold is in flight', async () => {
    const { user, network } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [`POST /api/reservations/${RESERVATION_ID}/hold`]: neverAnswers,
    })
    await priceTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    expect(await screen.findByRole('button', { name: 'Holding the equipment' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Change the dates or the tools' })).toBeDisabled()
    expect(network.requestsTo(holdRoute())).toHaveLength(1)
  })
})
