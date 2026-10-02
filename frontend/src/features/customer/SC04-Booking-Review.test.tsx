/**
 * Tests for the first step of a booking on SC-04, with the network replaced
 * at `fetch`.
 *
 * Reviewing creates the reservation as a draft and shows the server's figures.
 * It is one request, and each test reads what the screen made of the answer,
 * when it worked and when it did not. Holding is in
 * SC04-Booking-Hold.test.tsx and confirming in SC04-Booking-Confirm.test.tsx.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { basketSnapshot } from '../../shared/basket-store'
import { createdResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  BOOKING_WORKS,
  CREATE_REQUEST,
  CREATE_ROUTE,
  DRAFT,
  RESERVATION_ID,
} from '../../test/reservation-samples'
import { ACCESS_TOKEN, bearerOf } from '../../test/session-samples'
import { BASKET_STEP, REVIEW, REVIEW_STEP, figure, openBasket, stepHeading } from './SC04-test-kit'

const SERVER_SAID_ON_HOLD = 'This customer account is on hold, so it cannot make a reservation.'

/** Press the review button and wait for the draft to be on the page. */
async function review(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(screen.getByRole('button', { name: REVIEW }))
  return stepHeading(REVIEW_STEP)
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('reviewing the basket', () => {
  it('creates the reservation as a draft from the basket, with the session token', async () => {
    const user = userEvent.setup()
    const network = await openBasket(BOOKING_WORKS)

    await review(user)

    const [request] = network.requestsTo(CREATE_ROUTE)
    expect(request.body).toEqual(CREATE_REQUEST)
    expect(bearerOf(request)).toBe(ACCESS_TOKEN)
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
    expect(basketSnapshot().reservationId).toBe(RESERVATION_ID)
  })

  it('moves focus to the heading of the step, and says what happened', async () => {
    const user = userEvent.setup()
    await openBasket(BOOKING_WORKS)

    const heading = await review(user)

    expect(heading).toHaveFocus()
    expect(screen.getByText('Your basket has been priced. Nothing is held yet.')).toHaveAttribute(
      'role',
      'status',
    )
    expect(screen.getByRole('list', { name: 'Booking steps' })).toHaveTextContent(
      'Step 1, Review the cost, this step',
    )
  })

  it('shows every line and the figures the server sent, and does no sum of its own', async () => {
    const user = userEvent.setup()
    await openBasket(BOOKING_WORKS)

    await review(user)

    // None of these follow from the rates or from each other.
    expect(screen.getByRole('table')).toHaveTextContent('CP 100 Plate Compactor')
    expect(screen.getByRole('table')).toHaveTextContent(/2 units, R 340[,.]00 a day or R 1.360[,.]00 a week/)
    expect(screen.getByRole('table')).toHaveTextContent(/R 1.500[,.]00 deposit each/)
    expect(figure('Hire before VAT, 4 days')).toHaveTextContent(/^R 1.111[,.]11$/)
    expect(figure('VAT')).toHaveTextContent(/^R 333[,.]33$/)
    expect(figure('Total with VAT')).toHaveTextContent(/^R 4.444[,.]44$/)
    expect(figure('Deposit')).toHaveTextContent(/^R 5.555[,.]55$/)
    expect(
      screen.getByText(
        'The deposit is held when you collect the equipment and returned to you after you bring it back.',
      ),
    ).toBeVisible()
    expect(screen.getByText('Cape Town CBD')).toBeVisible()
    expect(screen.queryByText(/Priced with your discount/)).not.toBeInTheDocument()
  })

  it('says so when the server priced the basket with a discount', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () => createdResponse({ ...DRAFT, discountPercent: '12.50' }),
    })

    await review(user)

    expect(screen.getByText(/^Priced with your discount of 12[,.]5%\.$/)).toBeVisible()
  })

  it('disables the button while the request is in flight, and sends it once', async () => {
    const user = userEvent.setup()
    const network = await openBasket({ ...BOOKING_WORKS, [CREATE_ROUTE]: neverAnswers })

    await user.click(screen.getByRole('button', { name: REVIEW }))

    const waiting = await screen.findByRole('button', { name: 'Working out the cost' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
    // The basket cannot change underneath the request either.
    expect(screen.getByLabelText('How many')).toBeDisabled()
  })

  it('puts what the API refuses under the field it is about', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () =>
        problemResponse(422, {
          detail: 'Some of the details were not accepted. Check each one and try again.',
          errors: {
            fields: {
              'body.to': 'A hire can be at most 28 days.',
              'body.lines.0.quantity': 'Enter 10 or less.',
              'body.notes': 'Notes are not taken online.',
            },
          },
        }),
    })

    await user.click(screen.getByRole('button', { name: REVIEW }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We cannot book those details')
    expect(alert).toHaveTextContent('Some of the details were not accepted.')
    expect(alert).toHaveTextContent('Notes are not taken online.')
    expect(alert).not.toHaveTextContent('Enter 10 or less.')
    expect(screen.getByLabelText('Bring back on')).toBeInvalid()
    expect(screen.getByLabelText('Bring back on')).toHaveAccessibleDescription(
      /A hire can be at most 28 days\./,
    )
    expect(screen.getByLabelText('How many')).toHaveAccessibleDescription('Enter 10 or less.')
    expect(screen.getByRole('heading', { level: 2, name: BASKET_STEP })).toBeVisible()
  })

  it('takes a refusal down once the basket is changed', async () => {
    const user = userEvent.setup()
    await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () =>
        problemResponse(422, { errors: { fields: { 'body.lines.0.quantity': 'Enter 1 or less.' } } }),
    })
    await user.click(screen.getByRole('button', { name: REVIEW }))
    await screen.findByText('Enter 1 or less.')

    await user.click(screen.getByRole('button', { name: 'One fewer CP 100 Plate Compactor' }))

    expect(screen.queryByText('Enter 1 or less.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows a customer on hold the server sentence and no way to book', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () =>
        problemResponse(403, { slug: 'account-on-hold', detail: SERVER_SAID_ON_HOLD }),
    })

    await user.click(screen.getByRole('button', { name: REVIEW }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Your account cannot book at the moment')
    expect(alert).toHaveTextContent(SERVER_SAID_ON_HOLD)
    expect(screen.queryByRole('button', { name: REVIEW })).not.toBeInTheDocument()
    // Changing the basket does not bring the button back.
    await user.click(screen.getByRole('button', { name: 'One more CP 100 Plate Compactor' }))
    expect(screen.queryByRole('button', { name: REVIEW })).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(SERVER_SAID_ON_HOLD)
    expect(network.requestsTo(CREATE_ROUTE)).toHaveLength(1)
  })

  it('says so in plain words when the request fails, and prices the basket on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBasket({
      ...BOOKING_WORKS,
      [CREATE_ROUTE]: () => problemResponse(500, { requestId: 'req-create-9' }),
    })

    await user.click(screen.getByRole('button', { name: REVIEW }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not price your basket')
    expect(alert).toHaveTextContent('req-create-9')
    expect(alert).not.toHaveTextContent('500')

    network.setRoute(CREATE_ROUTE, () => createdResponse(DRAFT))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await stepHeading(REVIEW_STEP)).toBeVisible()
  })
})
