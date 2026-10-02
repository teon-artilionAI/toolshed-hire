/**
 * Tests for what becomes of a draft when the person goes back to the basket on
 * SC-04, with the network replaced at `fetch`.
 *
 * A review makes a draft on the server. Going back and reviewing again must
 * not leave one behind each time. A basket that did not change carries on with
 * the draft it has. A basket that did change has the old draft cancelled, and
 * only then is the new one made.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { basketSnapshot, setBasketQuantity } from '../../shared/basket-store'
import { createdResponse, jsonResponse, problemResponse } from '../../test/api-mock'
import type { ApiMock } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  BOOKING_WORKS,
  CANCELLED,
  CREATE_ROUTE,
  DRAFT,
  HELD,
  RESERVATION_ID,
  SECOND_REFERENCE,
  SECOND_RESERVATION_ID,
  cancelRoute,
  detailRoute,
} from '../../test/reservation-samples'
import { CUSTOMER } from '../../test/session-samples'
import {
  BASKET_STEP,
  CHANGE_BASKET,
  REVIEW,
  REVIEW_STEP,
  openBasket,
  stepHeading,
} from './SC04-test-kit'

const ONE_MORE = 'One more CP 100 Plate Compactor'
const SECOND_DRAFT = { ...DRAFT, id: SECOND_RESERVATION_ID, reference: SECOND_REFERENCE }

/** Every reservation request so far, in the order it was sent. */
function reservationRequests(network: ApiMock): string[] {
  return network.requests
    .filter((request) => request.path.startsWith('/api/reservations'))
    .map((request) => `${request.method} ${request.path}`)
}

/** Review the basket, then go back to it. */
async function reviewAndGoBack(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole('button', { name: REVIEW }))
  await stepHeading(REVIEW_STEP)
  await user.click(screen.getByRole('button', { name: CHANGE_BASKET }))
  await stepHeading(BASKET_STEP)
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('going back to the basket from the review', () => {
  it('sets the draft aside, sends nothing, and moves focus to the basket', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)

    await reviewAndGoBack(user)

    expect(screen.getByRole('heading', { level: 2, name: BASKET_STEP })).toHaveFocus()
    expect(reservationRequests(network)).toEqual([CREATE_ROUTE])
    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().setAside).toEqual({ reservationId: RESERVATION_ID, fitsBasket: true })
  })

  it('carries on with the same draft when the basket did not change, and makes no other', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [detailRoute()]: () => jsonResponse(DRAFT) })
    await reviewAndGoBack(user)

    await user.click(screen.getByRole('button', { name: REVIEW }))

    expect(await stepHeading(REVIEW_STEP)).toHaveFocus()
    expect(reservationRequests(network)).toEqual([CREATE_ROUTE, detailRoute()])
    expect(basketSnapshot().reservationId).toBe(RESERVATION_ID)
    expect(basketSnapshot().setAside).toBeNull()
  })

  it('cancels the draft before it makes another when the basket changed', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)
    await reviewAndGoBack(user)
    network.setRoute(CREATE_ROUTE, () => createdResponse(SECOND_DRAFT))

    await user.click(screen.getByRole('button', { name: ONE_MORE }))
    await user.click(screen.getByRole('button', { name: REVIEW }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
    expect(reservationRequests(network)).toEqual([CREATE_ROUTE, cancelRoute(), CREATE_ROUTE])
    expect(network.requestsTo(cancelRoute())[0].body).toEqual({ reason: null })
    expect(network.requestsTo(CREATE_ROUTE)[1].body).toMatchObject({ lines: [{ quantity: 3 }] })
    expect(basketSnapshot().reservationId).toBe(SECOND_RESERVATION_ID)
    expect(basketSnapshot().setAside).toBeNull()
  })

  it.each([
    ['is not there any more', () => problemResponse(404)],
    ['was cancelled somewhere else', () => jsonResponse(CANCELLED)],
  ])('makes a new reservation when the draft it set aside %s', async (_what, answer) => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [detailRoute()]: answer })
    await reviewAndGoBack(user)
    network.setRoute(CREATE_ROUTE, () => createdResponse(SECOND_DRAFT))

    await user.click(screen.getByRole('button', { name: REVIEW }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
    expect(reservationRequests(network)).toEqual([CREATE_ROUTE, detailRoute(), CREATE_ROUTE])
    expect(basketSnapshot().reservationId).toBe(SECOND_RESERVATION_ID)
  })

  it('goes on to the new reservation when the server says the old one was already over', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [cancelRoute()]: () => problemResponse(409, { slug: 'state-transition' }),
    })
    await reviewAndGoBack(user)
    network.setRoute(CREATE_ROUTE, () => createdResponse(SECOND_DRAFT))

    await user.click(screen.getByRole('button', { name: ONE_MORE }))
    await user.click(screen.getByRole('button', { name: REVIEW }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(basketSnapshot().reservationId).toBe(SECOND_RESERVATION_ID)
  })

  it('says so and makes nothing new when the old draft cannot be cancelled, then works on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [cancelRoute()]: () => problemResponse(500, { requestId: 'req-cancel-3' }),
    })
    await reviewAndGoBack(user)
    await user.click(screen.getByRole('button', { name: ONE_MORE }))

    await user.click(screen.getByRole('button', { name: REVIEW }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not price your basket')
    expect(alert).toHaveTextContent('req-cancel-3')
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
    expect(basketSnapshot().setAside).toEqual({ reservationId: RESERVATION_ID, fitsBasket: false })

    network.setRoute(cancelRoute(), () => jsonResponse(CANCELLED))
    network.setRoute(CREATE_ROUTE, () => createdResponse(SECOND_DRAFT))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
    expect(network.requestsTo(cancelRoute())).toHaveLength(2)
    expect(basketSnapshot().reservationId).toBe(SECOND_RESERVATION_ID)
  })
})

describe('a basket that changed while a reservation was under way', () => {
  it('has that reservation cancelled before the next one, so a hold does not keep its units', async () => {
    const user = userEvent.setup()
    const network = await openBasket(
      { ...BOOKING_WORKS, [detailRoute()]: () => jsonResponse(HELD) },
      CUSTOMER,
      RESERVATION_ID,
    )
    await stepHeading('Step 2 of 3. Hold the equipment')
    network.setRoute(CREATE_ROUTE, () => createdResponse(SECOND_DRAFT))

    // The catalogue changes the basket through the store, from another screen.
    setBasketQuantity(DRAFT.lines[0].modelSlug, 1)
    await stepHeading(BASKET_STEP)
    await user.click(screen.getByRole('button', { name: REVIEW }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
    expect(reservationRequests(network)).toEqual([detailRoute(), cancelRoute(), CREATE_ROUTE])
  })
})
