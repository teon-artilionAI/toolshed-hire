/**
 * Tests for SC-15 Return and Condition Inspection as it reads, with the
 * network replaced at `fetch`.
 *
 * The screen reads the hire by the key in the address. Loading, failed and not
 * found, then a hire with every unit out, the late fee of each unit as the
 * server sent it, a hire partly back, one settled, one that owes a balance and
 * one waiting for a damage report. Taking units back is in
 * SC15-Return-Writes.test.tsx, and what the files share is in SC15-test-kit.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL, RENTAL_ID, RENTAL_REFERENCE } from '../../test/counter-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import {
  LATE_FEE_CHARGE,
  ODD_FEE_TODAY,
  OVERDUE_HIRE,
  OWES_A_BALANCE,
  PARTLY_BACK,
  SETTLED_HIRE,
  WAITING_FOR_DAMAGE,
  rentalRoute,
} from '../../test/rental-samples'
import { LATE_FEE_IS_THE_SYSTEMS, ONLY_THE_OWNER_WAIVES } from './SC15-ItemInspection'
import { findUnitsStillOut, openReturn, showing } from './SC15-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** The value against one line of the settlement table. */
function settlementLine(label: string): string {
  const row = screen.getByRole('rowheader', { name: label }).closest('tr')
  if (!row) throw new Error(`The settlement has no line called ${label}.`)
  return row.textContent ?? ''
}

describe('while the hire loads', () => {
  it('says so and shows no figure', async () => {
    await openReturn({ [rentalRoute()]: neverAnswers })

    expect(await screen.findByText('Loading the hire', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
})

describe('when the hire cannot be read', () => {
  it('says so with the reference, and reads it again on a retry', async () => {
    const { user, network } = await openReturn({ [rentalRoute()]: () => problemResponse(500, { requestId: 'req-hire-3' }) })

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load this hire')
    expect(within(alert).getByText('req-hire-3')).toBeVisible()

    network.setRoute(rentalRoute(), () => jsonResponse(RENTAL))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await findUnitsStillOut()).toBeVisible()
  })

  it('says plainly when no hire has that key or reference', async () => {
    await openReturn(
      { [rentalRoute('TSH-H-26-999999')]: () => problemResponse(404, { detail: 'No such hire.' }) },
      'TSH-H-26-999999',
      'We cannot find that hire',
    )

    expect(screen.getByText('No hire matches "TSH-H-26-999999"')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open the overdue worklist' })).toHaveAttribute('href', '/counter/overdue')
  })
})

describe('a hire with every unit out', () => {
  it('is read by its key, and shows each unit with what it went out as', async () => {
    const { network } = await openReturn(showing(RENTAL))
    const out = await findUnitsStillOut()

    expect(network.requestsTo(rentalRoute())).toHaveLength(1)
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.getByText(`Every unit on ${RENTAL_REFERENCE} is still out`)).toBeVisible()
    expect(within(out).getByRole('group', { name: 'TSH-PC-0007' })).toHaveTextContent(
      'Went out at B, good working order, 1250 hours on the meter.',
    )
    expect(within(out).getAllByText('Not late. If it comes back today there is no late fee.')).toHaveLength(2)
    expect(screen.queryByText('Deposit settlement')).not.toBeInTheDocument()
  })

  it('shows the late fee of each unit exactly as the server worked it out, and offers no way to change it', async () => {
    await openReturn(showing(OVERDUE_HIRE))
    const out = await findUnitsStillOut()

    const first = within(out).getByRole('group', { name: 'TSH-PC-0007' })
    expect(within(first).getByText(`2 days late. Late fee if it comes back today ${money(ODD_FEE_TODAY)}.`)).toBeVisible()
    expect(within(first).getByText(LATE_FEE_IS_THE_SYSTEMS)).toBeVisible()
    expect(within(first).getByText(ONLY_THE_OWNER_WAIVES)).toBeVisible()
    expect(screen.queryByRole('textbox', { name: /fee/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(screen.getByText('Overdue', { selector: '.pill' })).toBeVisible()
  })

  it('opens the grade at the one each unit went out at, and the meter at its reading then', async () => {
    const { user } = await openReturn(showing(RENTAL))
    await findUnitsStillOut()

    await user.click(screen.getByRole('checkbox', { name: /^TSH-PC-0007 is back on the counter/ }))
    await user.click(screen.getByRole('checkbox', { name: /^TSH-PC-0011 is back on the counter/ }))

    expect(screen.getAllByLabelText('Condition coming back').map((select) => (select as HTMLSelectElement).value)).toEqual(['B', 'A'])
    expect(screen.getByLabelText('Hour meter reading')).toHaveValue('1250')
    expect(screen.getByText('This unit has no hour meter, so there is nothing to read.')).toBeVisible()
  })
})

describe('a hire partly back', () => {
  it('says it is partially returned, shows the unit that is back and when, and offers only the one out', async () => {
    await openReturn(showing(PARTLY_BACK))
    const out = await findUnitsStillOut()

    expect(screen.getByText(`${RENTAL_REFERENCE} is partially returned`)).toBeVisible()
    expect(screen.getByText(/1 of 2 units are still out/)).toBeVisible()
    expect(within(out).queryByRole('group', { name: 'TSH-PC-0007' })).not.toBeInTheDocument()
    expect(within(out).getByRole('group', { name: 'TSH-PC-0011' })).toBeVisible()
    const back = screen.getByText('Units already back').closest('section') as HTMLElement
    expect(within(back).getByText(/Back 12 Mar 2026 at 10:15 at B, good working order, 1262 hours on the meter\./)).toBeVisible()
    expect(within(back).getByText(/Late fee charged R 444[,.]44\./)).toBeVisible()
  })
})

describe('a hire with every unit back', () => {
  it('shows the settlement exactly as the server worked it out, with why each rand was withheld', async () => {
    await openReturn(showing(SETTLED_HIRE))

    expect(await screen.findByText(`${RENTAL_REFERENCE} is settled`, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.queryByRole('region', { name: 'The units still out' })).not.toBeInTheDocument()
    expect(settlementLine('Deposit held at collection')).toContain(money('5555.55'))
    expect(settlementLine('Withheld from the deposit')).toContain(money('444.44'))
    expect(settlementLine('Released to the customer')).toContain(money('4999.99'))
    expect(settlementLine('Balance due')).toContain(money('0.00'))
    expect(screen.getByText(`Late fee. ${LATE_FEE_CHARGE.description}`)).toBeVisible()
    expect(screen.getByText(/Nothing is due\./)).toBeVisible()
    expect(document.body.textContent).not.toMatch(/-\s?R\s\d|R\s-\d/)
  })

  it('shows the balance due and a form for the payment when the deposit did not cover it', async () => {
    await openReturn(showing(OWES_A_BALANCE))

    expect(await screen.findByText('The deposit does not cover the charges', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(/owes a balance of R 777[,.]77/)).toBeVisible()
    expect(screen.getByRole('form', { name: 'Pay the balance' })).toBeVisible()
    expect(screen.getByLabelText('Payment reference')).toBeVisible()
    expect(screen.getByRole('button', { name: /^Record the payment of R 777[,.]77$/ })).toBeEnabled()
  })

  it('says the deposit is waiting for a damage report, and links each unit to its report', async () => {
    await openReturn(showing(WAITING_FOR_DAMAGE))

    expect(await screen.findByText('The deposit is waiting for a damage report', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Record the damage to TSH-PC-0007' })).toHaveAttribute(
      'href',
      `/counter/damage/TSH-PC-0007?rentalItem=${WAITING_FOR_DAMAGE.items[0].id}`,
    )
    expect(screen.queryByRole('link', { name: /TSH-PC-0011/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Pay the balance' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Waiting for a damage report.')).toBeVisible())
  })
})

describe('opened by the reference', () => {
  it('reads the hire by the reference in the address', async () => {
    const { network } = await openReturn({ [rentalRoute(RENTAL_REFERENCE)]: () => jsonResponse(RENTAL) }, RENTAL_REFERENCE)

    await findUnitsStillOut()
    expect(network.requestsTo(rentalRoute(RENTAL_REFERENCE))).toHaveLength(1)
    expect(network.requestsTo(rentalRoute(RENTAL_ID))).toHaveLength(0)
  })
})
