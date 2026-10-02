/**
 * Tests for the second step of a booking on SC-04, with the network replaced
 * at `fetch`.
 *
 * Holding takes the equipment for thirty minutes. It is one request, and each
 * test reads what the screen made of the answer. A conflict shows the server's
 * own sentence, which names the model and the dates, and lets the person
 * change the basket.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { basketSnapshot } from '../../shared/basket-store'
import { createdResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  BOOKING_WORKS,
  CREATE_ROUTE,
  DRAFT,
  HELD,
  HOLD_UNTIL_CLOCK,
  cancelRoute,
  holdRoute,
} from '../../test/reservation-samples'
import {
  BASKET_STEP,
  CHANGE_BASKET,
  HOLD,
  HOLD_STEP,
  REVIEW,
  REVIEW_STEP,
  openBasket,
  stepHeading,
} from './SC04-test-kit'

const SERVER_SAID_NO_STOCK =
  'CP 100 Plate Compactor cannot be supplied at Cape Town CBD from 2026-03-12 to 2026-03-16.'
const SERVER_SAID_ON_HOLD = 'This customer account is on hold, so it cannot make a reservation.'

/** Press the review button and wait for the draft to be on the page. */
async function review(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(screen.getByRole('button', { name: REVIEW }))
  return stepHeading(REVIEW_STEP)
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('holding the equipment', () => {
  it('holds the draft, moves focus to the step, and says until when', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)
    await review(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    expect(await stepHeading(HOLD_STEP)).toHaveFocus()
    expect(network.requestsTo(holdRoute())).toHaveLength(1)
    expect(network.requestsTo(holdRoute())[0].body).toBeUndefined()
    expect(screen.getByText(`Held until ${HOLD_UNTIL_CLOCK}.`)).toBeVisible()
    expect(screen.getByText(`The equipment is held for you until ${HOLD_UNTIL_CLOCK}.`)).toHaveAttribute(
      'role',
      'status',
    )
    expect(screen.getByRole('timer', { name: 'Time left to confirm' })).toHaveTextContent('30:00')
  })

  it('offers the hold only when the server says the draft can be held', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () => createdResponse({ ...DRAFT, canHold: false }),
    })

    await review(user)

    expect(screen.queryByRole('button', { name: HOLD })).not.toBeInTheDocument()
    expect(screen.getByText('This basket cannot be held right now')).toBeVisible()
    expect(screen.getByRole('button', { name: CHANGE_BASKET })).toBeEnabled()
  })

  it('disables the button while the hold is in flight', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [holdRoute()]: neverAnswers })
    await review(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    const waiting = await screen.findByRole('button', { name: 'Holding the equipment' })
    expect(waiting).toBeDisabled()
    expect(screen.getByRole('button', { name: CHANGE_BASKET })).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(holdRoute())).toHaveLength(1)
  })

  it('shows the server sentence on a conflict, and lets the person change the basket', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [holdRoute()]: () =>
        problemResponse(409, { slug: 'asset-unavailable', detail: SERVER_SAID_NO_STOCK }),
    })
    await review(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not hold everything in your basket')
    expect(alert).toHaveTextContent(SERVER_SAID_NO_STOCK)
    expect(screen.getByRole('heading', { level: 2, name: REVIEW_STEP })).toBeVisible()

    await user.click(screen.getByRole('button', { name: CHANGE_BASKET }))

    expect(await stepHeading(BASKET_STEP)).toHaveFocus()
    expect(screen.getByRole('button', { name: REVIEW })).toBeEnabled()
    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().lines).toHaveLength(1)
    // A draft holds nothing, so there is nothing to release.
    expect(network.requestsTo(cancelRoute())).toHaveLength(0)
  })

  it('takes the hold away from a customer whose account went on hold in the meantime', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [holdRoute()]: () =>
        problemResponse(403, { slug: 'account-on-hold', detail: SERVER_SAID_ON_HOLD }),
    })
    await review(user)

    await user.click(screen.getByRole('button', { name: HOLD }))

    expect(await screen.findByRole('alert')).toHaveTextContent(SERVER_SAID_ON_HOLD)
    expect(screen.queryByRole('button', { name: HOLD })).not.toBeInTheDocument()
  })

  it('says so when the hold fails some other way, and holds on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [holdRoute()]: () => problemResponse(500) })
    await review(user)

    await user.click(screen.getByRole('button', { name: HOLD }))
    expect(await screen.findByRole('alert')).toHaveTextContent('We could not hold the equipment')

    network.setRoute(holdRoute(), () => jsonResponse(HELD))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await stepHeading(HOLD_STEP)).toBeVisible()
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})
