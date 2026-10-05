/**
 * Tests for SC-08 Reservation Detail and Cancellation, with the network
 * replaced at `fetch`.
 *
 * The screen is opened on the reference of one booking as the signed in
 * customer. Each test sets how the detail route and the cancellation route
 * answer and reads the page. Whether cancelling is offered follows the flag
 * the server sent, and what the screen shows after a cancellation is what the
 * server answered.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Reservation } from '../../shared/api/contract'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { findScreenHeading, renderApp } from '../../test/render-app'
import {
  CANCELLED,
  CONFIRMED,
  HELD,
  REFERENCE,
  cancelRoute,
  detailRoute,
} from '../../test/reservation-samples'
import { CUSTOMER, signedInAs } from '../../test/session-samples'

const DETAIL = detailRoute(REFERENCE)
const OPEN_QUESTION = 'Cancel this booking'
const YES = 'Yes, cancel this booking'
const REASON = 'Why are you cancelling? You can leave this empty.'
const CANCELLED_TITLE = 'This booking has been cancelled'
const SERVER_SAID_TOO_LATE = 'This booking was collected at 09:10, so it can no longer be cancelled.'
const TYPED_REASON = 'The job has been postponed'
const CANCELLED_WITH_REASON: Reservation = { ...CANCELLED, cancellationReason: TYPED_REASON }

async function openBooking(routes: RouteTable, heading: string = REFERENCE): Promise<ApiMock> {
  const network = mockApi({ ...signedInAs(CUSTOMER), ...routes })
  renderApp(`/reservations/${REFERENCE}`)
  await findScreenHeading(heading)
  return network
}

/** The figure shown against one term in the list of figures. */
function figure(term: string): HTMLElement {
  const value = screen.getByText(term).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`No figure is shown for "${term}".`)
  return value
}

async function openQuestion(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole('button', { name: OPEN_QUESTION }))
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('the booking', () => {
  it('is read by the reference in the address, and shows its lines and the figures the server sent', async () => {
    const network = await openBooking({ [DETAIL]: () => jsonResponse(CONFIRMED) })

    expect(network.requestsTo(DETAIL)).toHaveLength(1)
    expect(screen.getByText('Booked on 12 Mar 2026 at 08:00 by Wesley Adonis.')).toBeVisible()
    expect(screen.getByText('Confirmed', { selector: 'span' })).toBeVisible()
    expect(screen.getByRole('table')).toHaveTextContent('CP 100 Plate Compactor')
    expect(screen.getByRole('table')).toHaveTextContent(/2 units, R 340[,.]00 a day/)
    expect(figure('Hire before VAT, 4 days')).toHaveTextContent(/^R 1.111[,.]11$/)
    expect(figure('VAT')).toHaveTextContent(/^R 333[,.]33$/)
    expect(figure('Total with VAT')).toHaveTextContent(/^R 4.444[,.]44$/)
    expect(figure('Deposit')).toHaveTextContent(/^R 5.555[,.]55$/)
    expect(screen.getByText('12 Mar 2026 to 16 Mar 2026')).toBeVisible()
    expect(screen.getByText('Cape Town CBD')).toBeVisible()
    expect(figure('Confirmed on')).toHaveTextContent('12 Mar 2026 at 08:05')
    expect(screen.getByRole('link', { name: 'All my hires' })).toHaveAttribute('href', '/reservations')
  })

  it('says until when a held booking is held', async () => {
    await openBooking({ [DETAIL]: () => jsonResponse(HELD) })

    expect(screen.getByText('Held for you', { selector: 'span' })).toBeVisible()
    expect(figure('Held until')).toHaveTextContent('12 Mar 2026 at 08:30')
  })

  it('shows no sample charges, and says when the hire is charged', async () => {
    await openBooking({ [DETAIL]: () => jsonResponse(CONFIRMED) })

    const charges = screen.getByRole('heading', { name: 'Charges' }).closest('section')
    expect(charges).toHaveTextContent('Nothing has been charged on this booking. The hire is charged once the equipment is collected')
    expect(charges).not.toHaveTextContent(/R\s\d/)
    expect(screen.queryByText(/Late fee|Deposit held|under way/)).not.toBeInTheDocument()
    expect(screen.getByText(/Bring the identity document on your account/)).toBeVisible()
  })

  it.each([
    ['COLLECTED', 'The equipment has been collected, so this booking is now a hire.'],
    ['RETURNED', 'The equipment has come back, so this hire is finished.'],
  ] as const)('points a %s booking to the hire history for its charges', async (status, said) => {
    await openBooking({ [DETAIL]: () => jsonResponse({ ...CONFIRMED, status, canCancel: false }) })

    const charges = screen.getByRole('heading', { name: 'Charges' }).closest('section') as HTMLElement
    expect(charges).toHaveTextContent(said)
    expect(charges).not.toHaveTextContent(/Nothing has been charged/)
    expect(within(charges).getByRole('link', { name: 'See your hire history' })).toHaveAttribute('href', '/account')
    expect(screen.queryByText(/Bring the identity document/)).not.toBeInTheDocument()
  })

  it.each(['CANCELLED', 'EXPIRED', 'NO_SHOW'] as const)(
    'says nothing was charged on a booking %s before it went out',
    async (status) => {
      await openBooking({ [DETAIL]: () => jsonResponse({ ...CONFIRMED, status, canCancel: false }) })

      const charges = screen.getByRole('heading', { name: 'Charges' }).closest('section')
      expect(charges).toHaveTextContent('Nothing was charged on this booking, because the equipment never went out.')
    },
  )
})

describe('while it is loading and when it cannot be loaded', () => {
  it('announces that the booking is loading', async () => {
    await openBooking({ [DETAIL]: neverAnswers }, 'Booking detail')

    expect(screen.getByText('Loading this booking')).toHaveAttribute('role', 'status')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows a plain not found state for a booking that belongs to another account', async () => {
    await openBooking({ [DETAIL]: () => problemResponse(404) }, 'We cannot find that booking')

    expect(screen.getByText('No booking with that reference')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Back to my hires' })).toHaveAttribute('href', '/reservations')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: OPEN_QUESTION })).not.toBeInTheDocument()
  })

  it('says so in plain words when it fails, and loads on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBooking(
      { [DETAIL]: () => problemResponse(500, { requestId: 'req-detail-2' }) },
      'Booking detail',
    )

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load this booking')
    expect(within(alert).getByText('req-detail-2')).toBeVisible()

    network.setRoute(DETAIL, () => jsonResponse(CONFIRMED))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await findScreenHeading(REFERENCE)).toBeVisible()
  })
})

describe('whether cancelling is offered', () => {
  it('is offered when the server says the booking can be cancelled', async () => {
    await openBooking({ [DETAIL]: () => jsonResponse(CONFIRMED) })

    expect(screen.getByRole('button', { name: OPEN_QUESTION })).toBeEnabled()
  })

  it('is not offered when the server says it cannot, whatever the status', async () => {
    await openBooking({ [DETAIL]: () => jsonResponse({ ...CONFIRMED, canCancel: false }) })

    expect(screen.queryByRole('button', { name: OPEN_QUESTION })).not.toBeInTheDocument()
    expect(screen.getByText(/This booking cannot be cancelled online/)).toBeVisible()
  })

  it.each([
    ['COLLECTED', 'The equipment has been collected, so the booking can no longer be cancelled. Bring it back to Cape Town CBD by the return date.'],
    ['RETURNED', 'The equipment has come back and the hire is finished, so there is nothing to cancel.'],
    ['EXPIRED', 'The hold ran out before the booking was confirmed, so there is nothing to cancel.'],
    ['NO_SHOW', 'The equipment was not collected on the day, so the booking was closed. There is nothing to cancel.'],
  ] as const)('says why a %s booking has nothing to cancel, and never to ring about it', async (status, said) => {
    await openBooking({ [DETAIL]: () => jsonResponse({ ...CONFIRMED, status, canCancel: false }) })

    expect(screen.getByText(said)).toBeVisible()
    expect(screen.queryByText(/cannot be cancelled online/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: OPEN_QUESTION })).not.toBeInTheDocument()
  })

  it('shows what the server recorded for a booking that is already cancelled', async () => {
    await openBooking({ [DETAIL]: () => jsonResponse(CANCELLED_WITH_REASON) })

    const notice = screen.getByText(CANCELLED_TITLE).closest('[role="status"]')
    expect(notice).toHaveTextContent('It was cancelled on 12 Mar 2026 at 09:15.')
    expect(notice).toHaveTextContent(`The reason given was "${TYPED_REASON}".`)
    expect(screen.queryByRole('button', { name: OPEN_QUESTION })).not.toBeInTheDocument()
  })

  it.each(['Testing the live site.', 'Is the branch open?', 'Plans changed!'])(
    'ends the sentence once when the reason "%s" ends one already',
    async (reason) => {
      await openBooking({ [DETAIL]: () => jsonResponse({ ...CANCELLED, cancellationReason: reason }) })

      const notice = screen.getByText(CANCELLED_TITLE).closest('[role="status"]')
      expect(notice).toHaveTextContent(`The reason given was "${reason}"`)
      expect(notice?.textContent).not.toContain(`"${reason}".`)
    },
  )
})

describe('cancelling', () => {
  it('asks first, with focus on the question, and can be backed out of', async () => {
    const user = userEvent.setup()
    const network = await openBooking({ [DETAIL]: () => jsonResponse(CONFIRMED) })

    await openQuestion(user)

    expect(screen.getByRole('heading', { name: `Cancel ${REFERENCE}?` })).toHaveFocus()
    expect(screen.getByLabelText(REASON)).toHaveAccessibleDescription('Up to 200 characters.')
    expect(screen.getByLabelText(REASON)).toHaveAttribute('maxlength', '200')

    await user.click(screen.getByRole('button', { name: 'Keep the booking' }))

    expect(screen.queryByRole('heading', { name: `Cancel ${REFERENCE}?` })).not.toBeInTheDocument()
    expect(network.requestsTo(cancelRoute())).toHaveLength(0)
  })

  it('sends the reason that was typed, and shows the reservation the server answered with', async () => {
    const user = userEvent.setup()
    const network = await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: () => jsonResponse(CANCELLED_WITH_REASON),
    })
    await openQuestion(user)

    await user.type(screen.getByLabelText(REASON), `  ${TYPED_REASON}  `)
    await user.click(screen.getByRole('button', { name: YES }))

    const notice = (await screen.findByText(CANCELLED_TITLE)).closest('[role="status"]')
    expect(network.requestsTo(cancelRoute())[0].body).toEqual({ reason: TYPED_REASON })
    expect(notice).toHaveTextContent('It was cancelled on 12 Mar 2026 at 09:15.')
    expect(notice).toHaveTextContent(`The reason given was "${TYPED_REASON}".`)
    expect(screen.getByText('Cancelled', { selector: 'span' })).toBeVisible()
    expect(screen.queryByRole('button', { name: OPEN_QUESTION })).not.toBeInTheDocument()
    await waitFor(() => expect(notice?.parentElement).toHaveFocus())
    // The answer is shown as it came. The detail is not asked for again to get it.
    expect(network.requestsTo(DETAIL)).toHaveLength(1)
  })

  it('sends no reason when none was typed', async () => {
    const user = userEvent.setup()
    const network = await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: () => jsonResponse(CANCELLED),
    })
    await openQuestion(user)

    await user.click(screen.getByRole('button', { name: YES }))

    await screen.findByText(CANCELLED_TITLE)
    expect(network.requestsTo(cancelRoute())[0].body).toEqual({ reason: null })
    expect(screen.queryByText(/The reason given was/)).not.toBeInTheDocument()
  })

  it('disables the buttons while the request is in flight, and sends it once', async () => {
    const user = userEvent.setup()
    const network = await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: neverAnswers,
    })
    await openQuestion(user)

    await user.click(screen.getByRole('button', { name: YES }))

    const waiting = await screen.findByRole('button', { name: 'Cancelling this booking' })
    expect(waiting).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Keep the booking' })).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(cancelRoute())).toHaveLength(1)
  })

  it('shows the server sentence when it is too late, and stops offering the cancellation', async () => {
    const user = userEvent.setup()
    const network = await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: () =>
        problemResponse(409, { slug: 'state-transition', detail: SERVER_SAID_TOO_LATE }),
    })
    await openQuestion(user)
    network.setRoute(DETAIL, () =>
      jsonResponse({ ...CONFIRMED, status: 'COLLECTED', canCancel: false }),
    )

    await user.click(screen.getByRole('button', { name: YES }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This booking can no longer be cancelled')
    expect(alert).toHaveTextContent(SERVER_SAID_TOO_LATE)
    // The booking is read again, and the screen follows what the server now says.
    expect(await screen.findByText('Out with you', { selector: 'span' })).toBeVisible()
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: YES })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('alert')).toHaveTextContent(SERVER_SAID_TOO_LATE)
  })

  it('puts a refused reason under its field', async () => {
    const user = userEvent.setup()
    await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: () =>
        problemResponse(422, {
          detail: 'Some of the details were not accepted.',
          errors: { fields: { 'body.reason': 'Use 200 characters or fewer.' } },
        }),
    })
    await openQuestion(user)

    await user.click(screen.getByRole('button', { name: YES }))

    expect(await screen.findByText('Use 200 characters or fewer.')).toBeVisible()
    expect(screen.getByLabelText(REASON)).toBeInvalid()
    expect(screen.getByLabelText(REASON)).toHaveAccessibleDescription(
      'Up to 200 characters. Use 200 characters or fewer.',
    )
    expect(screen.getByRole('button', { name: YES })).toBeEnabled()
  })

  it('says so when the request fails some other way, and cancels on a retry', async () => {
    const user = userEvent.setup()
    const network = await openBooking({
      [DETAIL]: () => jsonResponse(CONFIRMED),
      [cancelRoute()]: () => problemResponse(500, { requestId: 'req-cancel-6' }),
    })
    await openQuestion(user)

    await user.click(screen.getByRole('button', { name: YES }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not cancel this booking')
    expect(within(alert).getByText('req-cancel-6')).toBeVisible()

    network.setRoute(cancelRoute(), () => jsonResponse(CANCELLED))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(CANCELLED_TITLE)).toBeVisible()
  })
})
