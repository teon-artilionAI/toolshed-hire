/**
 * Tests for the last step of a booking on SC-04 and for a hold that ends,
 * with the network replaced at `fetch`.
 *
 * Confirming books the hire. A hold ends when its time runs out on the screen
 * or when the server answers a confirmation with a conflict. Giving a hold up
 * and picking a booking up after a reload are in SC04-Booking-Resume.test.tsx.
 *
 * Only the date is pinned. The countdown ticks on a real timer, so a test
 * moves the pinned date and the next tick, within a second, reads it.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { basketSnapshot } from '../../shared/basket-store'
import { createdResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  BOOKING_WORKS,
  CONFIRMED,
  CREATE_ROUTE,
  DRAFT,
  HELD,
  HOLD_EXPIRES_AT,
  REFERENCE,
  SECOND_REFERENCE,
  SECOND_RESERVATION_ID,
  confirmRoute,
  holdRoute,
} from '../../test/reservation-samples'
import { CUSTOMER } from '../../test/session-samples'
import {
  CONFIRM,
  CONFIRMED_STEP,
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
const SERVER_SAID_HOLD_GONE = 'The hold on this reservation ran out at 08:30.'
const EMAIL_SENTENCE = /A confirmation email is on its way to you/
const UNVERIFIED = 'Your email address has not been verified'

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

describe('confirming the hire', () => {
  it('shows the reference and the email sentence, moves focus, and empties the basket', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    expect(await stepHeading(CONFIRMED_STEP)).toHaveFocus()
    expect(network.requestsTo(confirmRoute())).toHaveLength(1)
    const notice = screen.getByText(`Booking ${REFERENCE} is confirmed`).closest('[role="status"]')
    expect(notice).toHaveTextContent(EMAIL_SENTENCE)
    expect(notice).toHaveTextContent('Collect from Cape Town CBD on 12 Mar 2026')
    expect(screen.getByText(`Your hire is confirmed. The reference is ${REFERENCE}.`)).toHaveAttribute(
      'role',
      'status',
    )
    expect(screen.getByRole('link', { name: 'View this booking' })).toHaveAttribute(
      'href',
      `/reservations/${REFERENCE}`,
    )
    expect(basketSnapshot().lines).toEqual([])
    expect(screen.getByRole('link', { name: 'Basket, 0 items' })).toBeVisible()
  })

  it('does not say the hire is confirmed when the server answers with one that is still held', async () => {
    const user = userEvent.setup()
    await openBasket({ ...BOOKING_WORKS, [confirmRoute()]: () => jsonResponse(HELD) })
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    await waitFor(() => expect(screen.getByRole('button', { name: CONFIRM })).toBeEnabled())
    expect(screen.queryByText(EMAIL_SENTENCE)).not.toBeInTheDocument()
    expect(screen.queryByText(/is confirmed/)).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: HOLD_STEP })).toBeVisible()
    expect(basketSnapshot().lines).toHaveLength(1)
  })

  it('disables the button while the confirmation is in flight', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [confirmRoute()]: neverAnswers })
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    const waiting = await screen.findByRole('button', { name: 'Confirming your hire' })
    expect(waiting).toBeDisabled()
    expect(screen.getByRole('button', { name: RELEASE })).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(confirmRoute())).toHaveLength(1)
  })

  it('says the hold ran out when the server answers a conflict, and holds again from the basket', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [confirmRoute()]: () =>
        problemResponse(409, { slug: 'state-transition', detail: SERVER_SAID_HOLD_GONE }),
      [holdRoute(SECOND_RESERVATION_ID)]: () =>
        jsonResponse({ ...HELD, id: SECOND_RESERVATION_ID, reference: SECOND_REFERENCE }),
    })
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    expect(await screen.findByText(NO_LONGER_HELD)).toBeVisible()
    expect(screen.getByText(new RegExp(SERVER_SAID_HOLD_GONE))).toBeVisible()
    expect(screen.queryByRole('button', { name: CONFIRM })).not.toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()

    // A lapsed hold cannot be held again, so a new reservation is made and held.
    network.setRoute(CREATE_ROUTE, () =>
      createdResponse({ ...DRAFT, id: SECOND_RESERVATION_ID, reference: SECOND_REFERENCE }),
    )
    await user.click(screen.getByRole('button', { name: HOLD_AGAIN }))

    expect(await screen.findByRole('button', { name: CONFIRM })).toBeEnabled()
    expect(screen.getByRole('timer')).toHaveTextContent('30:00')
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(2)
    expect(network.requestsTo(holdRoute(SECOND_RESERVATION_ID))).toHaveLength(1)
    expect(basketSnapshot().reservationId).toBe(SECOND_RESERVATION_ID)
  })

  it('says plainly that the email address is not verified, and keeps the hold', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [confirmRoute()]: () => problemResponse(403, { slug: 'email-not-verified' }),
    })
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))

    expect(await screen.findByText(UNVERIFIED)).toBeVisible()
    expect(screen.getByText(/cannot be confirmed online until the email address/)).toBeVisible()
    expect(screen.getByRole('timer')).toBeVisible()
    expect(screen.queryByText(NO_LONGER_HELD)).not.toBeInTheDocument()
  })

  it('offers no confirmation when the server says it cannot be confirmed, and says why for an unverified address', async () => {
    const user = userEvent.setup()
    await openBasket(
      { ...BOOKING_WORKS, [holdRoute()]: () => jsonResponse({ ...HELD, canConfirm: false }) },
      { ...CUSTOMER, emailVerified: false },
    )

    await hold(user)

    expect(screen.queryByRole('button', { name: CONFIRM })).not.toBeInTheDocument()
    expect(screen.getByText(UNVERIFIED)).toBeVisible()
    expect(screen.getByRole('timer')).toBeVisible()
  })

  it('says so when the confirmation fails some other way, and confirms on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [confirmRoute()]: () => problemResponse(500) })
    await hold(user)

    await user.click(screen.getByRole('button', { name: CONFIRM }))
    expect(await screen.findByRole('alert')).toHaveTextContent('We could not confirm your hire')

    network.setRoute(confirmRoute(), () => jsonResponse(CONFIRMED))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await stepHeading(CONFIRMED_STEP)).toBeVisible()
  })
})

describe('the time on a hold', () => {
  it('is a timer that is not spoken by itself, beside a status that speaks only at a few marks', async () => {
    const user = userEvent.setup()
    await openBasket(BOOKING_WORKS)
    await hold(user)

    const timer = screen.getByRole('timer', { name: 'Time left to confirm' })
    expect(timer).toHaveAttribute('aria-live', 'off')
    expect(timer.closest('[role="status"]')).toBeNull()
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 2, name: HOLD_STEP }))

    // Twenty five minutes on, five are left. The figure follows the clock and
    // the spoken line says so once.
    vi.setSystemTime(new Date('2026-03-12T08:25:00+02:00'))
    await waitFor(() => expect(timer).toHaveTextContent('05:00'), { timeout: 3000 })
    expect(
      screen.getByText('5 minutes or less left to confirm before the hold runs out.'),
    ).toHaveAttribute('role', 'status')
    // Focus has not been taken from where the person was.
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 2, name: HOLD_STEP }))
  })

  it('says the hold has run out when it reaches zero, and offers to hold again and not to confirm', async () => {
    const user = userEvent.setup()
    await openBasket(BOOKING_WORKS)
    await hold(user)
    expect(screen.getByRole('button', { name: CONFIRM })).toBeEnabled()

    vi.setSystemTime(new Date(HOLD_EXPIRES_AT))

    expect(await screen.findByText(NO_LONGER_HELD, {}, { timeout: 3000 })).toBeVisible()
    expect(screen.getByText('The hold has run out. Hold it again to carry on.')).toHaveAttribute(
      'role',
      'status',
    )
    expect(screen.queryByRole('button', { name: CONFIRM })).not.toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: HOLD_AGAIN })).toBeEnabled()
    expect(basketSnapshot().lines).toHaveLength(1)
  })
})
