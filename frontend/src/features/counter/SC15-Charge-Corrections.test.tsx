/**
 * Tests for the charges on SC-15 and the owner's corrections of them, with the
 * network replaced at `fetch`.
 *
 * Every charge is listed. An administrator is offered what the server allows
 * for each charge, a waiver on a pending one and a reversal on a settled one
 * nothing reverses yet that is neither a movement of the deposit nor a
 * reversal itself, and an adjustment of the hire. Each asks first with a
 * reason, sends the body the contract names once, and shows the hire the
 * server answered with. A 409 or a 403 shows the server's sentence and a 422
 * lands under its box. Counter staff are offered none of it.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Rental } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_ID } from '../../test/counter-samples'
import {
  ADJUSTMENT_REASON,
  AFTER_ADJUSTMENT,
  AFTER_REVERSAL,
  AFTER_WAIVER,
  CORRECTABLE_HIRE,
  HIRE_CHARGE,
  PENDING_LATE_FEE,
  REVERSAL_REASON,
  WAIVER_REASON,
  adjustmentRoute,
  reversalRoute,
  waiverRoute,
} from '../../test/correction-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { rentalRoute } from '../../test/rental-samples'
import { ADMIN, COUNTER_STAFF, signedInAs } from '../../test/session-samples'
import type { SessionUser } from '../../shared/api/contract'
import { HEADING } from './SC15-test-kit'

const REVERSE_HIRE = new RegExp(`^Reverse the hire charge of ${money('4444.44')}`)
const WAIVE_LATE_FEE = new RegExp(`^Waive the late fee of ${money('444.44')}`)

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function openAs(
  person: SessionUser,
  rental: Rental,
  routes: RouteTable = {},
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(person), [rentalRoute()]: () => jsonResponse(rental), ...routes })
  renderApp(`/counter/return/${RENTAL_ID}`)
  await findScreenHeading(HEADING)
  await screen.findByRole('list', { name: /^Charges on / }, SCREEN_WAIT)
  return { user: userEvent.setup(), network }
}

function charge(name: string, index = 0): HTMLElement {
  const list = screen.getByRole('list', { name: /^Charges on / })
  return within(list).getAllByRole('article', { name })[index]
}

describe('the charges on a hire', () => {
  it('lists every charge with its amount and where it stands, and offers counter staff no correction', async () => {
    await openAs(COUNTER_STAFF, AFTER_REVERSAL)

    expect(within(charge('Hire')).getByText(HIRE_CHARGE.description)).toBeVisible()
    expect(within(charge('Hire')).getByText(money('4444.44'))).toBeVisible()
    expect(within(charge('Late fee')).getByText(/^Not settled yet\./)).toBeVisible()
    expect(screen.getByText(/^Only the owner can waive a charge\./)).toBeVisible()
    expect(screen.queryByRole('button', { name: /^(Waive|Reverse)/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust the hire' })).not.toBeInTheDocument()
  })

  it('says which charge a reversal reverses, and that the original is reversed, with the reason', async () => {
    await openAs(COUNTER_STAFF, AFTER_REVERSAL)

    const reversal = charge('Hire', 1)
    expect(within(reversal).getByText(`${money('4444.44')} back to the customer`)).toBeVisible()
    expect(within(reversal).getByText(`This reverses the hire charge of ${money('4444.44')} raised 12 Mar 2026 at 08:10.`)).toBeVisible()
    expect(within(reversal).getByText(REVERSAL_REASON)).toBeVisible()
    expect(within(charge('Hire', 0)).getByText('A later charge on this hire reverses this one.')).toBeVisible()
  })

  it('shows the reason a charge was waived', async () => {
    await openAs(COUNTER_STAFF, AFTER_WAIVER)

    const waived = charge('Late fee')
    expect(within(waived).getByText(/^Waived by the owner\./)).toBeVisible()
    expect(within(waived).getByText(WAIVER_REASON)).toBeVisible()
  })

  it('offers the owner a waiver on a pending charge, and no reversal the server would refuse', async () => {
    await openAs(ADMIN, AFTER_REVERSAL)

    expect(within(charge('Late fee')).getByRole('button', { name: WAIVE_LATE_FEE })).toBeVisible()
    // The original is reversed already, the reversal is not reversed again,
    // and a settled movement of the deposit is never reversed.
    expect(within(charge('Hire', 0)).queryByRole('button')).not.toBeInTheDocument()
    expect(within(charge('Hire', 1)).queryByRole('button')).not.toBeInTheDocument()
    expect(within(charge('Deposit held')).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Adjust the hire' })).toBeVisible()
    expect(screen.queryByText(/^Only the owner can waive a charge\./)).not.toBeInTheDocument()
  })
})

describe('a reversal', () => {
  it('asks first with a reason, then posts the reason once and shows the hire the server answered with', async () => {
    const { user, network } = await openAs(ADMIN, CORRECTABLE_HIRE, {
      [reversalRoute(HIRE_CHARGE.id)]: () => jsonResponse(AFTER_REVERSAL),
    })

    await user.click(within(charge('Hire')).getByRole('button', { name: REVERSE_HIRE }))
    const question = screen.getByRole('heading', { level: 4, name: `Reverse the hire charge of ${money('4444.44')}?` })
    expect(question).toHaveFocus()
    expect(screen.getByText(/A new hire charge for the same amount the other way is added/)).toBeVisible()

    await user.type(screen.getByLabelText('Why'), 'Oops')
    await user.click(screen.getByRole('button', { name: 'Yes, reverse it' }))
    expect(screen.getByLabelText('Why')).toHaveAccessibleDescription(/Write at least 5 characters\. This has 4\./)
    expect(network.requestsTo(reversalRoute(HIRE_CHARGE.id))).toHaveLength(0)

    await user.clear(screen.getByLabelText('Why'))
    await user.type(screen.getByLabelText('Why'), `  ${REVERSAL_REASON} `)
    await user.click(screen.getByRole('button', { name: 'Yes, reverse it' }))

    expect(await screen.findByText('The hire charge is reversed', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(reversalRoute(HIRE_CHARGE.id))).toHaveLength(1)
    expect(network.requestsTo(reversalRoute(HIRE_CHARGE.id))[0].body).toEqual({ reason: REVERSAL_REASON })
    expect(await screen.findByText(/^This reverses the hire charge of/, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(/Nothing is due\./)).toBeVisible()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openAs(ADMIN, CORRECTABLE_HIRE, { [reversalRoute(HIRE_CHARGE.id)]: neverAnswers })
    await user.click(within(charge('Hire')).getByRole('button', { name: REVERSE_HIRE }))
    await user.type(screen.getByLabelText('Why'), REVERSAL_REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, reverse it' }))

    const waiting = await screen.findByRole('button', { name: 'Reversing it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(reversalRoute(HIRE_CHARGE.id))).toHaveLength(1)
  })

  it.each([
    [409, 'That charge has been reversed already.'],
    [403, 'Only the owner can reverse a charge.'],
  ])('shows the server sentence for a %i', async (status, detail) => {
    const { user, network } = await openAs(ADMIN, CORRECTABLE_HIRE, {
      [reversalRoute(HIRE_CHARGE.id)]: () => problemResponse(status, { detail }),
    })
    await user.click(within(charge('Hire')).getByRole('button', { name: REVERSE_HIRE }))
    await user.type(screen.getByLabelText('Why'), REVERSAL_REASON)
    const reads = network.requestsTo(rentalRoute()).length

    await user.click(screen.getByRole('button', { name: 'Yes, reverse it' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The charge was not reversed')
    expect(alert).toHaveTextContent(detail)
    if (status === 409) await waitFor(() => expect(network.requestsTo(rentalRoute()).length).toBeGreaterThan(reads))
  })
})

describe('a waiver', () => {
  it('posts the reason once and shows the charge waived, and a refused reason lands under its box', async () => {
    const { user, network } = await openAs(ADMIN, CORRECTABLE_HIRE, {
      [waiverRoute(PENDING_LATE_FEE.id)]: () =>
        problemResponse(422, { errors: { fields: { 'body.reason': 'Say what happened, not just that it did.' } } }),
    })
    await user.click(within(charge('Late fee')).getByRole('button', { name: WAIVE_LATE_FEE }))
    expect(screen.getByText(/stops being owed\. It stays on TSH-H-26-000099 marked as waived/)).toBeVisible()
    await user.type(screen.getByLabelText('Why'), 'It happened')
    await user.click(screen.getByRole('button', { name: 'Yes, waive it' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Why')).toHaveAccessibleDescription(/Say what happened, not just that it did\./),
    )

    network.setRoute(waiverRoute(PENDING_LATE_FEE.id), () => jsonResponse(AFTER_WAIVER))
    await user.clear(screen.getByLabelText('Why'))
    await user.type(screen.getByLabelText('Why'), WAIVER_REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, waive it' }))

    expect(await screen.findByText('The late fee is waived', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(waiverRoute(PENDING_LATE_FEE.id)).at(-1)?.body).toEqual({ reason: WAIVER_REASON })
    expect(within(charge('Late fee')).getByText(WAIVER_REASON)).toBeVisible()
  })
})

describe('an adjustment of the hire', () => {
  it('checks the amount, says what will be added, and posts the amount with two decimals and the reason', async () => {
    const { user, network } = await openAs(ADMIN, CORRECTABLE_HIRE, { [adjustmentRoute()]: () => jsonResponse(AFTER_ADJUSTMENT) })

    await user.click(screen.getByRole('button', { name: 'Adjust the hire' }))
    expect(screen.getByRole('heading', { level: 3, name: 'Adjust TSH-H-26-000099' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Yes, add the adjustment' }))
    expect(screen.getByLabelText('Amount in rand, including VAT')).toHaveAccessibleDescription(/Enter the amount/)
    expect(screen.getByLabelText('Why')).toHaveAccessibleDescription(/Write the reason/)
    expect(network.requestsTo(adjustmentRoute())).toHaveLength(0)

    await user.type(screen.getByLabelText('Amount in rand, including VAT'), '-150')
    expect(screen.getByText(new RegExp(`An adjustment that gives ${money('150.00')} back to the customer, including VAT`))).toBeVisible()
    await user.type(screen.getByLabelText('Why'), ADJUSTMENT_REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, add the adjustment' }))

    expect(await screen.findByText('TSH-H-26-000099 is adjusted', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(adjustmentRoute())).toHaveLength(1)
    expect(network.requestsTo(adjustmentRoute())[0].body).toEqual({ amountIncVat: '-150.00', reason: ADJUSTMENT_REASON })
    expect(screen.getByText(new RegExp(`The balance due is ${money('294.44')}\\.`))).toBeVisible()
    expect(within(charge('Adjustment')).getByText(ADJUSTMENT_REASON)).toBeVisible()
  })

  it('puts a refused amount under its box', async () => {
    const { user } = await openAs(ADMIN, CORRECTABLE_HIRE, {
      [adjustmentRoute()]: () =>
        problemResponse(422, { errors: { fields: { 'body.amountIncVat': 'An adjustment may not be larger than the hire.' } } }),
    })
    await user.click(screen.getByRole('button', { name: 'Adjust the hire' }))
    await user.type(screen.getByLabelText('Amount in rand, including VAT'), '99999')
    await user.type(screen.getByLabelText('Why'), ADJUSTMENT_REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, add the adjustment' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Amount in rand, including VAT')).toHaveAccessibleDescription(
        /An adjustment may not be larger than the hire\./,
      ),
    )
  })
})
