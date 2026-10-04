/**
 * Tests for the owner's release of a unit and the search for a replacement on
 * SC-14, with the network replaced at `fetch`.
 *
 * An administrator is offered "Release this unit" on each unit, and counter
 * staff are not. The release asks first with a reason, posts it once and reads
 * the booking again. A booking short of a unit says how many are missing and
 * offers any member of staff a replacement, which posts the reallocation,
 * shows the new units and reads the booking again, or shows the server's
 * sentence when nothing is free.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReservationCheckout, SessionUser } from '../../shared/api/contract'
import { jsonResponse, mockApi, neverAnswers, noContentResponse, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { READY_CHECKOUT, checkoutRoute } from '../../test/counter-samples'
import {
  REALLOCATED,
  RELEASED_UNIT,
  SHORT_CHECKOUT,
  reallocationRoute,
  releaseRoute,
} from '../../test/correction-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { REFERENCE } from '../../test/reservation-samples'
import { ADMIN, COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const REASON = 'Needed for an urgent hire at the stadium'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function openAs(
  person: SessionUser,
  checkout: ReservationCheckout,
  routes: RouteTable = {},
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(person), [checkoutRoute()]: () => jsonResponse(checkout), ...routes })
  renderApp(`/counter/checkout/${REFERENCE}`)
  await findScreenHeading('Checkout and deposit')
  return { user: userEvent.setup(), network }
}

function release(tag: string): Promise<HTMLElement> {
  return screen.findByRole('button', { name: `Release this unit ${tag}` }, SCREEN_WAIT)
}

describe('releasing a unit', () => {
  it('is offered on each unit to the owner, and to nobody else', async () => {
    await openAs(ADMIN, READY_CHECKOUT)
    expect(await release('TSH-PC-0007')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Release this unit TSH-PC-0011' })).toBeVisible()
  })

  it('is not offered to counter staff', async () => {
    await openAs(COUNTER_STAFF, READY_CHECKOUT)
    await screen.findByRole('group', { name: 'TSH-PC-0007' }, SCREEN_WAIT)

    expect(screen.queryByRole('button', { name: /^Release this unit/ })).not.toBeInTheDocument()
  })

  it('asks first with a reason, posts it once, and reads the booking again', async () => {
    const { user, network } = await openAs(ADMIN, READY_CHECKOUT, {
      [releaseRoute(RELEASED_UNIT.allocationId)]: () => noContentResponse(),
    })
    await user.click(await release('TSH-PC-0007'))

    expect(screen.getByRole('heading', { level: 4, name: `Release TSH-PC-0007 from ${REFERENCE}?` })).toBeVisible()
    expect(screen.getByText(new RegExp(`${REFERENCE} is then short a unit until it is reallocated`))).toBeVisible()
    expect(screen.getByLabelText('Why')).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Yes, release it' }))
    expect(screen.getByLabelText('Why')).toHaveAccessibleDescription(/Write the reason/)
    expect(network.requestsTo(releaseRoute(RELEASED_UNIT.allocationId))).toHaveLength(0)

    network.setRoute(checkoutRoute(), () => jsonResponse(SHORT_CHECKOUT))
    await user.type(screen.getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, release it' }))

    expect(await screen.findByText('TSH-PC-0007 is released', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(releaseRoute(RELEASED_UNIT.allocationId))).toHaveLength(1)
    expect(network.requestsTo(releaseRoute(RELEASED_UNIT.allocationId))[0].body).toEqual({ reason: REASON })
    expect(await screen.findByRole('heading', { level: 2, name: '1 unit is missing from this booking' }, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(SHORT_CHECKOUT.refusal ?? '')).toBeVisible()
    expect(network.requestsTo(checkoutRoute()).length).toBeGreaterThan(1)
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openAs(ADMIN, READY_CHECKOUT, { [releaseRoute(RELEASED_UNIT.allocationId)]: neverAnswers })
    await user.click(await release('TSH-PC-0007'))
    await user.type(screen.getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release it' }))

    const waiting = await screen.findByRole('button', { name: 'Releasing it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(releaseRoute(RELEASED_UNIT.allocationId))).toHaveLength(1)
  })

  it.each([
    [409, 'TSH-PC-0007 is already out on hire, so it cannot be released.'],
    [403, 'Only the owner can release a unit.'],
  ])('shows the server sentence for a %i', async (status, detail) => {
    const { user } = await openAs(ADMIN, READY_CHECKOUT, {
      [releaseRoute(RELEASED_UNIT.allocationId)]: () => problemResponse(status, { detail }),
    })
    await user.click(await release('TSH-PC-0007'))
    await user.type(screen.getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release it' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('TSH-PC-0007 was not released')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts a refused reason under its box', async () => {
    const { user } = await openAs(ADMIN, READY_CHECKOUT, {
      [releaseRoute(RELEASED_UNIT.allocationId)]: () =>
        problemResponse(422, { errors: { fields: { 'body.reason': 'The reason is too vague.' } } }),
    })
    await user.click(await release('TSH-PC-0007'))
    await user.type(screen.getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, release it' }))

    await waitFor(() => expect(screen.getByLabelText('Why')).toHaveAccessibleDescription(/The reason is too vague\./))
  })

  it('is offered on the units of a booking that cannot go out yet', async () => {
    await openAs(ADMIN, { ...READY_CHECKOUT, canCheckOut: false, refusal: 'It starts on 20 Mar 2026.' })

    const units = await screen.findByText('Units set aside for this booking', {}, SCREEN_WAIT)
    expect(units).toBeVisible()
    expect(screen.getByRole('button', { name: 'Release this unit TSH-PC-0007' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: /missing from this booking/ })).not.toBeInTheDocument()
  })
})

describe('a booking short of a unit', () => {
  it('says how many are missing, posts the reallocation once, shows the new units and reads the booking again', async () => {
    const { user, network } = await openAs(COUNTER_STAFF, SHORT_CHECKOUT, {
      [reallocationRoute()]: () => jsonResponse(REALLOCATED),
    })
    const short = await screen.findByRole('region', { name: '1 unit is missing from this booking' }, SCREEN_WAIT)
    expect(within(short).getByText(/needs 1 more unit before it can go out/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /^Release this unit/ })).not.toBeInTheDocument()

    network.setRoute(checkoutRoute(), () => jsonResponse(READY_CHECKOUT))
    await user.click(within(short).getByRole('button', { name: 'Find a replacement unit' }))

    expect(await screen.findByText(`${REALLOCATED.reference} has its units again`, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('Set aside now: TSH-PC-0012, TSH-PC-0011.')).toBeVisible()
    expect(network.requestsTo(reallocationRoute())).toHaveLength(1)
    expect(network.requestsTo(reallocationRoute())[0].body).toBeUndefined()
    expect(await screen.findByRole('heading', { level: 2, name: 'Step 1 of 3. Check each unit and take the deposit' }, SCREEN_WAIT)).toBeVisible()
  })

  it('shows the server sentence when no unit is free', async () => {
    const detail = 'No CP 100 Plate Compactor is free at Bellville from 12 Mar 2026 to 13 Mar 2026.'
    const { user } = await openAs(COUNTER_STAFF, SHORT_CHECKOUT, { [reallocationRoute()]: () => problemResponse(409, { detail }) })
    const short = await screen.findByRole('region', { name: '1 unit is missing from this booking' }, SCREEN_WAIT)

    await user.click(within(short).getByRole('button', { name: 'Find a replacement unit' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('No replacement was set aside')
    expect(alert).toHaveTextContent(detail)
  })

  it('names the button for more than one missing unit', async () => {
    await openAs(COUNTER_STAFF, { ...SHORT_CHECKOUT, units: [], unitsShort: 2 })

    expect(await screen.findByRole('button', { name: 'Find replacement units' }, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: '2 units are missing from this booking' })).toBeVisible()
  })
})
