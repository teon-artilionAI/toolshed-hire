/**
 * Tests for taking units back and paying a balance on SC-15, with the network
 * replaced at `fetch`.
 *
 * The form holds the return back until a unit is ticked and every answer is
 * right. Then it asks in words, sends exactly the body the contract names once,
 * and shows the hire the server answered with, partly back or settled. A 409
 * or a 403 shows the server's sentence, and a 422 puts its message under the
 * control it names. The balance payment sends its reference once and shows the
 * hire settled.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money } from '../../shared/format'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_REFERENCE } from '../../test/counter-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import {
  METERED,
  ODD_FEE_TODAY,
  OVERDUE_HIRE,
  OWES_A_BALANCE,
  PARTLY_BACK,
  SETTLED_HIRE,
  UNMETERED,
  balanceRoute,
  rentalRoute,
  returnsRoute,
} from '../../test/rental-samples'
import { ANSWER, ASK, QUESTION, findUnitsStillOut, openReturn, showing, tick } from './SC15-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Tick the metered unit, and record it as back at C with a new reading, a
 *  chuck key and a flag for damage. */
async function recordTheMeteredUnit(user: UserEvent): Promise<void> {
  await findUnitsStillOut()
  await tick(user, 'TSH-PC-0007')
  const unit = screen.getByRole('group', { name: 'TSH-PC-0007' })
  await user.selectOptions(within(unit).getByLabelText('Condition coming back'), 'C')
  await user.clear(within(unit).getByLabelText('Hour meter reading'))
  await user.type(within(unit).getByLabelText('Hour meter reading'), '1262')
  await user.type(within(unit).getByLabelText('Accessories that came back'), 'Chuck key')
  await user.click(within(unit).getByRole('checkbox', { name: /Flag for damage/ }))
}

describe('the return form', () => {
  it('sends nothing until a unit is ticked, and says so', async () => {
    const { user, network } = await openReturn(showing(OVERDUE_HIRE))
    await findUnitsStillOut()

    await user.click(screen.getByRole('button', { name: ASK }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Nothing has been taken back yet. 1 answer needs fixing.')
    expect(alert).toHaveTextContent('Tick each unit that is back on the counter.')
    expect(network.requestsTo(returnsRoute())).toHaveLength(0)
  })

  it('holds back a meter that reads less than it did going out', async () => {
    const { user, network } = await openReturn(showing(OVERDUE_HIRE))
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0007')
    await user.clear(screen.getByLabelText('Hour meter reading'))
    await user.type(screen.getByLabelText('Hour meter reading'), '1200')

    await user.click(screen.getByRole('button', { name: ASK }))

    expect(screen.getByLabelText('Hour meter reading')).toHaveAccessibleDescription(/cannot read less than it did going out, 1250 hours/)
    expect(network.requestsTo(returnsRoute())).toHaveLength(0)
  })

  it('asks first in words with the server late fee, then sends exactly the body the contract names, once', async () => {
    const { user, network } = await openReturn(showing(OVERDUE_HIRE, { [returnsRoute()]: () => jsonResponse(SETTLED_HIRE) }))
    await recordTheMeteredUnit(user)
    await tick(user, 'TSH-PC-0011')

    await user.click(screen.getByRole('button', { name: ASK }))

    expect(await screen.findByRole('heading', { level: 2, name: QUESTION })).toHaveFocus()
    expect(screen.getByText(`2 units, TSH-PC-0007 and TSH-PC-0011, come back from Thandi Mokoena on ${RENTAL_REFERENCE}.`)).toBeVisible()
    expect(screen.getByText(/^TSH-PC-0007 comes back at C, worn but serviceable, worse than the B, good working order it went out at\.$/)).toBeVisible()
    expect(screen.getByText('TSH-PC-0007 is flagged for damage.')).toBeVisible()
    expect(screen.getByText(new RegExp(`^TSH-PC-0011 is 2 days late, and the system charges a late fee of ${money(ODD_FEE_TODAY)} for it`))).toBeVisible()
    expect(screen.getByText(/That is the last unit out/)).toBeVisible()
    expect(network.requestsTo(returnsRoute())).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: ANSWER }))

    await screen.findByText(`Every unit on ${RENTAL_REFERENCE} is back`, {}, SCREEN_WAIT)
    expect(network.requestsTo(returnsRoute())).toHaveLength(1)
    expect(network.requestsTo(returnsRoute())[0].body).toEqual({
      items: [
        { rentalItemId: METERED.id, conditionIn: 'C', hourMeterIn: 1262, accessoriesIn: 'Chuck key', notes: null, flaggedForDamage: true },
        { rentalItemId: UNMETERED.id, conditionIn: 'A', hourMeterIn: null, accessoriesIn: null, notes: null, flaggedForDamage: false },
      ],
    })
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openReturn(showing(OVERDUE_HIRE, { [returnsRoute()]: neverAnswers }))
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0011')
    await user.click(screen.getByRole('button', { name: ASK }))

    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const waiting = await screen.findByRole('button', { name: 'Taking the units back' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(returnsRoute())).toHaveLength(1)
  })
})

describe('what the server answers', () => {
  it('shows the hire partially returned when a unit is still out, and moves focus to it', async () => {
    const { user } = await openReturn(showing(OVERDUE_HIRE, { [returnsRoute()]: () => jsonResponse(PARTLY_BACK) }))
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0007')
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const said = await screen.findByText('1 unit is still out, so the deposit stays held.', {}, SCREEN_WAIT)
    await waitFor(() => expect(said.closest('[tabindex="-1"]')).toHaveFocus())
    expect(screen.getAllByText(`${RENTAL_REFERENCE} is partially returned`).length).toBeGreaterThan(0)
    const out = await findUnitsStillOut()
    expect(within(out).queryByRole('group', { name: 'TSH-PC-0007' })).not.toBeInTheDocument()
    expect(within(out).getByRole('checkbox', { name: /^TSH-PC-0011 is back/ })).not.toBeChecked()
    expect(screen.getByText('Units already back')).toBeVisible()
  })

  it('shows the settlement from the server figures once the last unit is back', async () => {
    const { user } = await openReturn(showing(PARTLY_BACK, { [returnsRoute()]: () => jsonResponse(SETTLED_HIRE) }))
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0011')
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    expect(await screen.findByText('The deposit is settled below.', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('Deposit settlement')).toBeVisible()
    expect(screen.getByText(`${RENTAL_REFERENCE} is settled`)).toBeVisible()
    expect(screen.queryByRole('region', { name: 'The units still out' })).not.toBeInTheDocument()
  })

  it.each([
    [409, 'TSH-PC-0011 is already back, so it cannot be returned again.'],
    [403, 'This hire went out from Cape Town CBD, not from your branch.'],
  ])('shows the server sentence for a %i and offers to read the hire again', async (status, detail) => {
    const { user, network } = await openReturn(
      showing(OVERDUE_HIRE, { [returnsRoute()]: () => problemResponse(status, { detail }) }),
    )
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0011')
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The units were not taken back')
    expect(alert).toHaveTextContent(detail)
    const before = network.requestsTo(rentalRoute()).length
    await user.click(within(alert).getByRole('button', { name: 'Load the hire again' }))
    await waitFor(() => expect(network.requestsTo(rentalRoute()).length).toBeGreaterThan(before))
  })

  it('sends a refused field back to the form, under the control it names', async () => {
    const refused: RouteTable = {
      [returnsRoute()]: () =>
        problemResponse(422, { errors: { fields: { 'body.items.0.hourMeterIn': 'The meter went backwards.' } } }),
    }
    const { user } = await openReturn(showing(OVERDUE_HIRE, refused))
    await findUnitsStillOut()
    await tick(user, 'TSH-PC-0007')
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    await waitFor(() =>
      expect(screen.getByLabelText('Hour meter reading')).toHaveAccessibleDescription(/The meter went backwards\./),
    )
  })
})

describe('the payment of a balance', () => {
  it('needs a reference, then sends it once and shows the hire settled', async () => {
    const { user, network } = await openReturn(
      showing(OWES_A_BALANCE, { [balanceRoute()]: () => jsonResponse({ ...SETTLED_HIRE, balanceDue: '0.00' }) }),
    )
    const pay = await screen.findByRole('button', { name: /^Record the payment of/ }, SCREEN_WAIT)

    await user.click(pay)
    expect(screen.getByLabelText('Payment reference')).toHaveAccessibleDescription(/Enter the reference of the payment/)
    expect(network.requestsTo(balanceRoute())).toHaveLength(0)

    await user.type(screen.getByLabelText('Payment reference'), '  EFT-2026-0042 ')
    await user.click(pay)

    expect(await screen.findByText('The payment of the balance is recorded.', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(balanceRoute())).toHaveLength(1)
    expect(network.requestsTo(balanceRoute())[0].body).toEqual({ paymentReference: 'EFT-2026-0042' })
    expect(screen.queryByRole('form', { name: 'Pay the balance' })).not.toBeInTheDocument()
  })

  it('shows the server sentence when nothing is due any more', async () => {
    const detail = 'Nothing is due on TSH-H-26-000099.'
    const { user } = await openReturn(showing(OWES_A_BALANCE, { [balanceRoute()]: () => problemResponse(409, { detail }) }))
    await user.type(await screen.findByLabelText('Payment reference', {}, SCREEN_WAIT), 'EFT-1')

    await user.click(screen.getByRole('button', { name: /^Record the payment of/ }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The payment was not recorded')
    expect(alert).toHaveTextContent(detail)
  })
})
