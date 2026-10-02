/**
 * Tests for leaving a booking and coming back to one on SC-04, with the
 * network replaced at `fetch`.
 *
 * A person who gives a hold up to change the basket has the hold cancelled
 * first, so the equipment is free for the next attempt. A booking that was
 * under way before a reload is read back and carried on from where it stands,
 * and no second reservation is made.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { basketSnapshot } from '../../shared/basket-store'
import { jsonResponse, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  BASKET_READS,
  BOOKING_WORKS,
  CANCELLED,
  CREATE_ROUTE,
  DRAFT,
  EXPIRED,
  HELD,
  RESERVATION_ID,
  cancelRoute,
  detailRoute,
} from '../../test/reservation-samples'
import { CUSTOMER } from '../../test/session-samples'
import {
  BASKET_STEP,
  CONFIRM,
  HOLD,
  HOLD_STEP,
  REVIEW,
  REVIEW_STEP,
  openBasket,
  stepHeading,
} from './SC04-test-kit'

const HOLD_AGAIN = 'Hold it again'
const RELEASE = 'Release the hold and change my basket'
const NO_LONGER_HELD = 'The equipment is no longer held'

/** Go from the basket to a held reservation, the way a person does. */
async function hold(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole('button', { name: REVIEW }))
  await stepHeading(REVIEW_STEP)
  await user.click(screen.getByRole('button', { name: HOLD }))
  await stepHeading(HOLD_STEP)
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('giving a hold up to change the basket', () => {
  it('cancels the held reservation first, so the equipment is free again', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)
    await hold(user)

    await user.click(screen.getByRole('button', { name: RELEASE }))

    expect(await stepHeading(BASKET_STEP)).toHaveFocus()
    expect(network.requestsTo(cancelRoute())).toHaveLength(1)
    expect(network.requestsTo(cancelRoute())[0].body).toEqual({ reason: null })
    expect(basketSnapshot().reservationId).toBeNull()
    expect(basketSnapshot().lines).toHaveLength(1)
  })

  it('stays on the hold and says so when the release fails', async () => {
    const user = userEvent.setup()
    await openBasket({ ...BOOKING_WORKS, [cancelRoute()]: () => problemResponse(500) })
    await hold(user)

    await user.click(screen.getByRole('button', { name: RELEASE }))

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not release the hold')
    expect(screen.getByRole('heading', { level: 2, name: HOLD_STEP })).toBeVisible()
    expect(basketSnapshot().reservationId).toBe(RESERVATION_ID)
  })

  it('goes back to the basket when the server says the hold was already gone', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [cancelRoute()]: () => problemResponse(409, { slug: 'state-transition' }),
    })
    await hold(user)

    await user.click(screen.getByRole('button', { name: RELEASE }))

    expect(await stepHeading(BASKET_STEP)).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('a booking that was under way before a reload', () => {
  it.each([
    ['a draft', DRAFT, REVIEW_STEP],
    ['a hold', HELD, HOLD_STEP],
  ])('is picked up as %s, without making another reservation', async (_what, stored, heading) => {
    const network = await openBasket(
      { ...BOOKING_WORKS, [detailRoute()]: () => jsonResponse(stored) },
      CUSTOMER,
      RESERVATION_ID,
    )

    expect(await stepHeading(heading)).toBeVisible()
    expect(network.requestsTo(detailRoute())).toHaveLength(1)
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(0)
  })

  it('offers to hold again when the hold ran out in the meantime', async () => {
    await openBasket(
      { ...BOOKING_WORKS, [detailRoute()]: () => jsonResponse(EXPIRED) },
      CUSTOMER,
      RESERVATION_ID,
    )

    expect(await screen.findByText(NO_LONGER_HELD)).toBeVisible()
    expect(screen.getByRole('button', { name: HOLD_AGAIN })).toBeEnabled()
    expect(screen.queryByRole('button', { name: CONFIRM })).not.toBeInTheDocument()
  })

  it.each([
    ['it belongs to another account', () => problemResponse(404)],
    ['it was cancelled somewhere else', () => jsonResponse(CANCELLED)],
  ])('goes back to the basket when %s', async (_what, answer) => {
    await openBasket({ ...BASKET_READS, [detailRoute()]: answer }, CUSTOMER, RESERVATION_ID)

    expect(await stepHeading(BASKET_STEP)).toBeVisible()
    expect(screen.getByRole('button', { name: REVIEW })).toBeEnabled()
    await waitFor(() => expect(basketSnapshot().reservationId).toBeNull())
    expect(basketSnapshot().lines).toHaveLength(1)
  })

  it('says so when it cannot be read back, and lets the person start again from the basket', async () => {
    const user = userEvent.setup()
    await openBasket(
      { ...BASKET_READS, [detailRoute()]: () => problemResponse(500) },
      CUSTOMER,
      RESERVATION_ID,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not load the booking you had started',
    )

    await user.click(screen.getByRole('button', { name: 'Start again from my basket' }))

    expect(await stepHeading(BASKET_STEP)).toBeVisible()
  })
})
