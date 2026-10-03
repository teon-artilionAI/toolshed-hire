/**
 * Tests for SC-13 when a step of a counter booking does not work, with the
 * network replaced at `fetch`.
 *
 * A conflict on the hold shows the server's own sentence, which names the
 * model and the dates, and lets the assistant change the tools. A customer
 * whose account went on hold is shown the server's message and offered no way
 * to book. A refused field is shown under its field. A hold that ran out is
 * said plainly. Anything else is the shared error state with a retry.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, problemResponse } from '../../test/api-mock'
import { PLATE_COMPACTOR, TEST_NOW } from '../../test/catalogue-samples'
import {
  COUNTER_BOOKING_WORKS,
  COUNTER_HELD,
  modelAvailabilityAtBellville,
  modelAvailabilityRoute,
} from '../../test/counter-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { CREATE_ROUTE, cancelRoute, confirmRoute, holdRoute } from '../../test/reservation-samples'
import {
  CHANGE_TOOLS,
  CONFIRM,
  HELD_STEP,
  HOLD,
  LINES_STEP,
  PRICE,
  addTwoCompactors,
  openBooking,
  priceTwoCompactors,
  stepHeading,
} from './SC13-test-kit'

const SERVER_SAID_NO_STOCK =
  'CP 100 Plate Compactor cannot be supplied at Bellville from 2026-03-12 to 2026-03-13.'
const SERVER_SAID_ON_HOLD = 'This customer account is on hold, so it cannot make a reservation.'
const SERVER_SAID_LAPSED = 'The hold on TSH-R-26-000124 ran out at 08:30.'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('a conflict on the hold', () => {
  it('shows the server sentence and lets the assistant change the tools, giving the draft up', async () => {
    const { user, network } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [holdRoute()]: () => problemResponse(409, { slug: 'asset-unavailable', detail: SERVER_SAID_NO_STOCK }),
    })
    await priceTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not hold the equipment')
    expect(alert).toHaveTextContent(SERVER_SAID_NO_STOCK)
    expect(screen.queryByRole('button', { name: HOLD })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: CHANGE_TOOLS }))

    expect(await stepHeading(LINES_STEP)).toHaveFocus()
    expect(network.requestsTo(cancelRoute())).toHaveLength(1)
    // The tools are as the assistant left them, ready to change.
    expect(screen.getByLabelText('How many')).toHaveValue(2)
    expect(screen.getByRole('button', { name: `Remove ${PLATE_COMPACTOR.name}` })).toBeEnabled()
  })
})

describe('a customer whose account is on hold', () => {
  it('shows the server message and offers no way to book', async () => {
    const { user } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [CREATE_ROUTE]: () => problemResponse(403, { slug: 'account-on-hold', detail: SERVER_SAID_ON_HOLD }),
    })
    await addTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: PRICE }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('No booking can be made for Thandi Mokoena')
    expect(alert).toHaveTextContent(SERVER_SAID_ON_HOLD)
    expect(screen.queryByRole('button', { name: PRICE })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: HOLD })).not.toBeInTheDocument()
  })
})

describe('a refused field', () => {
  it('puts each message under the date or the line it names', async () => {
    const { user } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [CREATE_ROUTE]: () =>
        problemResponse(422, {
          detail: 'Two fields were refused.',
          errors: {
            fields: {
              'body.from': 'The branch is closed on that day.',
              'body.lines.0.quantity': 'No more than two of this model at a time.',
            },
          },
        }),
    })
    await addTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: PRICE }))

    await waitFor(() =>
      expect(screen.getByLabelText('Goes out on')).toHaveAccessibleDescription('The branch is closed on that day.'),
    )
    expect(screen.getByLabelText('How many')).toHaveAccessibleDescription('No more than two of this model at a time.')
    expect(screen.getByRole('alert')).toHaveTextContent('Two fields were refused.')
  })
})

describe('a hold that ran out before the confirmation', () => {
  it('says so in the server words and offers the way back, not the confirmation', async () => {
    const { user } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [confirmRoute()]: () => problemResponse(409, { slug: 'hold-expired', detail: SERVER_SAID_LAPSED }),
    })
    await priceTwoCompactors(user)
    await user.click(screen.getByRole('button', { name: HOLD }))
    await stepHeading(HELD_STEP)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    expect(await screen.findByText('The hold has run out')).toBeVisible()
    expect(screen.getByText(new RegExp(SERVER_SAID_LAPSED))).toBeVisible()
    expect(screen.queryByRole('button', { name: CONFIRM })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: CHANGE_TOOLS })).toBeEnabled()
  })
})

describe('a step that fails some other way', () => {
  it('says so, and holds on a retry', async () => {
    const { user, network } = await openBooking({ ...COUNTER_BOOKING_WORKS, [holdRoute()]: () => problemResponse(500) })
    await priceTwoCompactors(user)

    await user.click(screen.getByRole('button', { name: HOLD }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not hold the equipment')

    network.setRoute(holdRoute(), () => jsonResponse(COUNTER_HELD))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await stepHeading(HELD_STEP)).toBeVisible()
  })
})

describe('a line that is not free', () => {
  it('says so for the quantity asked about', async () => {
    const { user } = await openBooking({
      ...COUNTER_BOOKING_WORKS,
      [modelAvailabilityRoute()]: (request) =>
        jsonResponse(modelAvailabilityAtBellville(request.query.get('quantity') === '1', 2)),
    })

    await addTwoCompactors(user)

    expect(
      await screen.findByText(/2 units not free at Bellville for these dates/, {}, SCREEN_WAIT),
    ).toBeVisible()
  })
})
