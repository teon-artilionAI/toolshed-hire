/**
 * Tests for SC-14 Checkout and Deposit, with the network replaced at `fetch`.
 *
 * The screen reads what the counter needs from the API by the reference in the
 * address. A reservation the server says cannot go out shows the server's
 * sentence and no form, and one already out says so and links to the hire.
 * Otherwise the assistant reads each tag, signs the agreement, is asked in
 * words, and one request makes the hire. A refusal shows the server's
 * sentence, and anything else is the shared error state.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { createdResponse, jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  READY_CHECKOUT,
  RENTAL,
  RENTAL_ID,
  RENTAL_REFERENCE,
  checkoutRoute,
  handoverRoute,
} from '../../test/counter-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { REFERENCE } from '../../test/reservation-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const HEADING = 'Checkout and deposit'
const ASK = 'Check out the equipment'
const ANSWER = 'Yes, hand it over'
const FORM_STEP = 'Step 1 of 3. Check each unit and take the deposit'
const QUESTION_STEP = 'Step 2 of 3. Hand the equipment over to Thandi Mokoena?'
const DONE_STEP = `Step 3 of 3. The equipment is out on hire ${RENTAL_REFERENCE}`

async function openCheckout(routes: RouteTable): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(COUNTER_STAFF), ...routes })
  renderApp(`/counter/checkout/${REFERENCE}`)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Read both tags, put the meter forward and sign the agreement. */
async function fillIn(user: UserEvent): Promise<void> {
  await user.click(await screen.findByRole('checkbox', { name: /it says TSH-PC-0007/ }, SCREEN_WAIT))
  await user.click(screen.getByRole('checkbox', { name: /it says TSH-PC-0011/ }))
  await user.clear(screen.getByLabelText('Hour meter reading'))
  await user.type(screen.getByLabelText('Hour meter reading'), '1262')
  await user.type(screen.getAllByLabelText('Accessories handed over')[1], 'Chuck key')
  await user.click(screen.getByRole('checkbox', { name: /read the hire agreement and signed it/ }))
}

const READY: RouteTable = {
  [checkoutRoute()]: () => jsonResponse(READY_CHECKOUT),
  [handoverRoute()]: () => createdResponse(RENTAL),
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('a reservation that cannot go out', () => {
  it('shows the server sentence and no form', async () => {
    const refusal = 'TSH-R-26-000124 starts on 20 Mar 2026, so it cannot go out before then.'
    await openCheckout({ [checkoutRoute()]: () => jsonResponse({ ...READY_CHECKOUT, canCheckOut: false, refusal }) })

    expect(await screen.findByText(refusal, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: ASK })).not.toBeInTheDocument()
  })

  it('says a collected one is already out, and links to the hire', async () => {
    await openCheckout({
      [checkoutRoute()]: () => jsonResponse({ ...READY_CHECKOUT, status: 'COLLECTED', canCheckOut: false, refusal: 'It is out.', rentalId: RENTAL_ID }),
    })

    expect(await screen.findByText(`${REFERENCE} is already out`, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open the hire' })).toHaveAttribute('href', `/counter/return/${RENTAL_ID}`)
    expect(screen.queryByRole('button', { name: ASK })).not.toBeInTheDocument()
  })

  it('says so when no booking has that reference', async () => {
    await openCheckout({ [checkoutRoute()]: () => problemResponse(404, { detail: 'No such reservation.' }) })

    expect(await findScreenHeading('We cannot find that booking')).toBeVisible()
  })
})

describe('the handover form', () => {
  it('is connected, and shows each unit, the deposit to take and the agreement', async () => {
    await openCheckout(READY)

    expect(await screen.findByRole('heading', { level: 2, name: FORM_STEP }, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'TSH-PC-0007' })).toBeVisible()
    expect(screen.getAllByLabelText('Condition going out').map((select) => (select as HTMLSelectElement).value)).toEqual(['B', 'A'])
    expect(screen.getByLabelText('Hour meter reading')).toHaveValue('1250')
    expect(screen.getByText('This unit has no hour meter, so there is nothing to read.')).toBeVisible()
    expect(screen.getByText(/^R 5.555[,.]55$/)).toBeVisible()
    expect(screen.getByText(/South African ID ending 5083/)).toBeVisible()
  })

  it('holds the handover back until every tag is read and the agreement is signed', async () => {
    const { user, network } = await openCheckout(READY)
    await screen.findByRole('heading', { level: 2, name: FORM_STEP }, SCREEN_WAIT)

    await user.click(screen.getByRole('button', { name: ASK }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Nothing has gone out yet. 3 answers need fixing.')
    expect(screen.getByRole('checkbox', { name: /it says TSH-PC-0007/ })).toHaveAccessibleDescription(/Read the tag on the unit/)
    expect(screen.getByRole('checkbox', { name: /signed it/ })).toBeInvalid()
    expect(network.requestsTo(handoverRoute())).toHaveLength(0)
  })

  it('asks first in words, then sends exactly the body the contract names, once, and shows the hire', async () => {
    const { user, network } = await openCheckout(READY)
    await fillIn(user)

    await user.click(screen.getByRole('button', { name: ASK }))

    expect(await screen.findByRole('heading', { level: 2, name: QUESTION_STEP })).toHaveFocus()
    expect(screen.getByText(/will go out to Thandi Mokoena from Bellville\. A deposit of R 5.555[,.]55/)).toBeVisible()
    expect(network.requestsTo(handoverRoute())).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: ANSWER }))

    expect(await screen.findByRole('heading', { level: 2, name: DONE_STEP })).toHaveFocus()
    expect(network.requestsTo(handoverRoute())).toHaveLength(1)
    expect(network.requestsTo(handoverRoute())[0].body).toEqual({
      items: [
        { allocationId: READY_CHECKOUT.units[0].allocationId, conditionOut: 'B', accessoriesOut: null, hourMeterOut: 1262 },
        { allocationId: READY_CHECKOUT.units[1].allocationId, conditionOut: 'A', accessoriesOut: 'Chuck key', hourMeterOut: null },
      ],
      agreementSigned: true,
    })
    const out = screen.getByRole('region', { name: DONE_STEP })
    expect(within(out).getByText(`Hire ${RENTAL_REFERENCE} is open`)).toBeVisible()
    expect(within(out).getByText('TSH-PC-0007')).toBeVisible()
    expect(within(out).getByText(/^R 5.555[,.]55$/)).toBeVisible()
    expect(within(out).getByText('13 Mar 2026')).toBeVisible()
  })

  it('keeps the hire on the screen when the booking is read again as collected', async () => {
    const { user, network } = await openCheckout(READY)
    await fillIn(user)
    network.setRoute(checkoutRoute(), () => jsonResponse({ ...READY_CHECKOUT, canCheckOut: false, rentalId: RENTAL_ID }))

    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    await screen.findByRole('heading', { level: 2, name: DONE_STEP }, SCREEN_WAIT)
    await waitFor(() => expect(network.requestsTo(checkoutRoute()).length).toBeGreaterThan(1))
    expect(screen.getByRole('heading', { level: 2, name: DONE_STEP })).toBeVisible()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openCheckout({ ...READY, [handoverRoute()]: neverAnswers })
    await fillIn(user)
    await user.click(screen.getByRole('button', { name: ASK }))

    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const waiting = await screen.findByRole('button', { name: 'Handing the equipment over' })
    expect(waiting).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Go back and change something' })).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(handoverRoute())).toHaveLength(1)
  })
})

describe('a handover the server refuses', () => {
  it.each([
    [409, 'TSH-R-26-000124 is not confirmed, so it cannot go out.'],
    [403, 'This reservation is collected at Cape Town CBD, not at your branch.'],
  ])('shows the server sentence for a %i and offers to read the booking again', async (status, detail) => {
    const { user, network } = await openCheckout({ ...READY, [handoverRoute()]: () => problemResponse(status, { detail }) })
    await fillIn(user)
    await user.click(screen.getByRole('button', { name: ASK }))

    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The equipment cannot go out')
    expect(alert).toHaveTextContent(detail)
    const before = network.requestsTo(checkoutRoute()).length
    await user.click(within(alert).getByRole('button', { name: 'Load the booking again' }))
    await waitFor(() => expect(network.requestsTo(checkoutRoute()).length).toBe(before + 1))
  })

  it('sends a refused field back to the form, under the control it names', async () => {
    const { user } = await openCheckout({
      ...READY,
      [handoverRoute()]: () =>
        problemResponse(422, { detail: 'One field was refused.', errors: { fields: { 'body.items.0.hourMeterOut': 'The meter went backwards.' } } }),
    })
    await fillIn(user)
    await user.click(screen.getByRole('button', { name: ASK }))

    await user.click(await screen.findByRole('button', { name: ANSWER }))

    expect(await screen.findByRole('heading', { level: 2, name: FORM_STEP })).toHaveFocus()
    expect(screen.getByLabelText('Hour meter reading')).toHaveAccessibleDescription(/The meter went backwards\./)
  })

  it('says so when the handover fails some other way, and sends it again on a retry', async () => {
    const { user, network } = await openCheckout({ ...READY, [handoverRoute()]: () => problemResponse(500) })
    await fillIn(user)
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not record the handover')

    network.setRoute(handoverRoute(), () => jsonResponse(RENTAL))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { level: 2, name: DONE_STEP })).toBeVisible()
    expect(network.requestsTo(handoverRoute())).toHaveLength(2)
  })
})
