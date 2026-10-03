/**
 * Tests for filing a damage report on SC-16, with the network replaced at
 * `fetch`.
 *
 * The form asks first in words, then sends exactly the body the contract names
 * once, for a customer charged on a hire, not charged, and outside a hire. A
 * 422 puts each of the server's messages under the field it names, among them
 * the refusal of an amount above the replacement value, and a 409 or a 403
 * shows the server's sentence. The answer gives the reference of the report,
 * and when it belongs to a hire the way back to its return, which reads the
 * hire afresh and shows the deposit settled.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_ID } from '../../test/counter-samples'
import {
  DAMAGED_ITEM,
  FILED_OFF_HIRE,
  FILED_ON_THE_HIRE,
  FILE_DAMAGE_ROUTE,
  ON_THE_SHELF,
  QUARANTINED_AT_BELLVILLE,
  SETTLED_AFTER_DAMAGE,
} from '../../test/damage-samples'
import { SCREEN_WAIT, currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import { WAITING_FOR_DAMAGE, rentalRoute } from '../../test/rental-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'
import { ANSWER, ASK, COMPLETE, RECOVERY, answer, openDamage, unitWith } from './SC16-test-kit'

const ON_THE_HIRE = `/counter/damage/${QUARANTINED_AT_BELLVILLE.assetTag}?rental=${RENTAL_ID}&rentalItem=${DAMAGED_ITEM.id}`
const OFF_HIRE = `/counter/damage/${ON_THE_SHELF.assetTag}`
const QUESTION = /^File this damage report for /

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('the body the form sends', () => {
  it('asks in words, then sends a chargeable report on a hire with the amount, once', async () => {
    const { user, network } = await openDamage(
      unitWith(QUARANTINED_AT_BELLVILLE, [], { [FILE_DAMAGE_ROUTE]: () => createdResponse(FILED_ON_THE_HIRE) }),
      ON_THE_HIRE,
    )
    await answer(user, { ...COMPLETE, estimate: 'R 456,78', recovery: '321.09' })

    await user.click(screen.getByRole('button', { name: ASK }))

    expect(await screen.findByRole('heading', { level: 2, name: QUESTION })).toHaveFocus()
    expect(screen.getByText('TSH-PC-0007 stays in quarantine and cannot be booked until the owner resolves the report.')).toBeVisible()
    expect(screen.getByText(/^The customer is charged R\s321[,.]09, including VAT, and it is withheld from the deposit/)).toBeVisible()
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: ANSWER }))

    expect(await screen.findByText('Damage report TSH-D-26-00031 is filed', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)[0].body).toEqual({
      assetTag: 'TSH-PC-0007',
      rentalItemId: DAMAGED_ITEM.id,
      severity: 'MAJOR',
      description: 'Base plate cracked across the weld.',
      repairEstimate: '456.78',
      chargeableToCustomer: true,
      recoveryAmount: '321.09',
    })
  })

  it('sends a report on a hire that does not charge the customer with no amount', async () => {
    const { user, network } = await openDamage(
      unitWith(QUARANTINED_AT_BELLVILLE, [], {
        [FILE_DAMAGE_ROUTE]: () => createdResponse({ ...FILED_ON_THE_HIRE, chargeableToCustomer: false, recoveryCharged: null }),
      }),
      ON_THE_HIRE,
    )
    await answer(user, { ...COMPLETE, charge: 'Do not charge the customer', recovery: undefined })
    await user.click(screen.getByRole('button', { name: ASK }))
    expect(await screen.findByText('The customer is not charged. Toolshed Hire absorbs the repair.')).toBeVisible()

    await user.click(screen.getByRole('button', { name: ANSWER }))

    await screen.findByText('Damage report TSH-D-26-00031 is filed', {}, SCREEN_WAIT)
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)[0].body).toMatchObject({
      rentalItemId: DAMAGED_ITEM.id,
      chargeableToCustomer: false,
      recoveryAmount: null,
    })
  })

  it('sends a report outside a hire with no rental item and no amount, and quarantines a unit on the shelf', async () => {
    const { user, network } = await openDamage(
      unitWith(ON_THE_SHELF, [], { [FILE_DAMAGE_ROUTE]: () => createdResponse(FILED_OFF_HIRE) }),
      OFF_HIRE,
    )
    await answer(user, { ...COMPLETE, severity: 'Not worth repairing', recovery: undefined })
    await user.click(screen.getByRole('button', { name: ASK }))
    expect(await screen.findByText('TSH-PC-0011 is quarantined and cannot be booked until the owner resolves the report.')).toBeVisible()

    await user.click(screen.getByRole('button', { name: ANSWER }))

    await screen.findByText('Damage report TSH-D-26-00032 is filed', {}, SCREEN_WAIT)
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)[0].body).toEqual({
      assetTag: 'TSH-PC-0011',
      rentalItemId: null,
      severity: 'WRITE_OFF',
      description: 'Base plate cracked across the weld.',
      repairEstimate: '456.78',
      chargeableToCustomer: true,
      recoveryAmount: null,
    })
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openDamage(unitWith(ON_THE_SHELF, [], { [FILE_DAMAGE_ROUTE]: neverAnswers }), OFF_HIRE)
    await answer(user, { ...COMPLETE, recovery: undefined })
    await user.click(screen.getByRole('button', { name: ASK }))

    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const waiting = await screen.findByRole('button', { name: 'Filing the report' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)).toHaveLength(1)
  })
})

describe('what the server refuses', () => {
  it('puts a refused amount back under the amount, with the most the server will take', async () => {
    const detail = 'The amount to recover cannot be more than R9876.54.'
    const { user } = await openDamage(
      unitWith(QUARANTINED_AT_BELLVILLE, [], {
        [FILE_DAMAGE_ROUTE]: () => problemResponse(422, { errors: { fields: { 'body.recoveryAmount': detail } } }),
      }),
      ON_THE_HIRE,
    )
    await answer(user, { ...COMPLETE, recovery: '99999' })
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    await waitFor(() => expect(screen.getByLabelText(RECOVERY)).toHaveAccessibleDescription(new RegExp(detail.replace(/\./g, '\\.'))))
    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has been filed yet. 1 answer needs fixing.')
  })

  it('lists a refusal of a field the form has no box for', async () => {
    const { user } = await openDamage(
      unitWith(QUARANTINED_AT_BELLVILLE, [], {
        [FILE_DAMAGE_ROUTE]: () =>
          problemResponse(422, { errors: { fields: { 'body.rentalItemId': 'We could not find that hire of this unit.' } } }),
      }),
      ON_THE_HIRE,
    )
    await answer(user, COMPLETE)
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    expect(await screen.findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent('We could not find that hire of this unit.')
  })

  it.each([
    [409, 'The deposit of this hire has already been settled, so the customer can no longer be charged.'],
    [403, 'This unit is held at Cape Town CBD, not at your branch.'],
  ])('shows the server sentence for a %i and files nothing', async (status, detail) => {
    const { user } = await openDamage(
      unitWith(QUARANTINED_AT_BELLVILLE, [], { [FILE_DAMAGE_ROUTE]: () => problemResponse(status, { detail }) }),
      ON_THE_HIRE,
    )
    await answer(user, COMPLETE)
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The report was not filed')
    expect(alert).toHaveTextContent(detail)
    expect(screen.queryByText(/is filed$/)).not.toBeInTheDocument()
  })
})

describe('once the report is filed', () => {
  it('gives the reference and, outside a hire, the way back to today and the locator', async () => {
    const { user } = await openDamage(
      unitWith(ON_THE_SHELF, [], { [FILE_DAMAGE_ROUTE]: () => createdResponse(FILED_OFF_HIRE) }),
      OFF_HIRE,
    )
    await answer(user, { ...COMPLETE, recovery: undefined })
    await user.click(screen.getByRole('button', { name: ASK }))
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    const said = await screen.findByText('Damage report TSH-D-26-00032 is filed', {}, SCREEN_WAIT)
    await waitFor(() => expect(said.closest('[tabindex="-1"]')).toHaveFocus())
    expect(screen.queryByRole('link', { name: /^Back to the return/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to today' })).toHaveAttribute('href', '/counter')
    expect(screen.getByRole('link', { name: 'Open the asset locator' })).toHaveAttribute('href', '/counter/locator?q=TSH-PC-0011')
  })

  it('says a unit already in the workshop stays there, as the server leaves it', async () => {
    const inTheWorkshop = { ...ON_THE_SHELF, status: 'UNDER_REPAIR' as const }
    const { user } = await openDamage(
      unitWith(inTheWorkshop, [], { [FILE_DAMAGE_ROUTE]: () => createdResponse(FILED_OFF_HIRE) }),
      OFF_HIRE,
    )
    await answer(user, { ...COMPLETE, recovery: undefined })
    await user.click(screen.getByRole('button', { name: ASK }))
    expect(await screen.findByText('TSH-PC-0011 stays in the workshop and cannot be booked until the owner resolves the report.')).toBeVisible()

    await user.click(screen.getByRole('button', { name: ANSWER }))

    expect(await screen.findByText(/^TSH-PC-0011 is in the workshop and cannot be booked/, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('New state of the unit').closest('div')).toHaveTextContent('In the workshop')
  })

  it('goes back to the return, which reads the hire again and shows the deposit settled', async () => {
    const network = mockApi({
      ...signedInAs(COUNTER_STAFF),
      ...unitWith(QUARANTINED_AT_BELLVILLE, [], { [FILE_DAMAGE_ROUTE]: () => createdResponse(FILED_ON_THE_HIRE) }),
      [rentalRoute()]: () => jsonResponse(WAITING_FOR_DAMAGE),
    })
    renderApp(`/counter/return/${RENTAL_ID}`)
    await findScreenHeading('Return and condition inspection')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('link', { name: 'Record the damage to TSH-PC-0007' }, SCREEN_WAIT))
    await findScreenHeading('Record damage')
    expect(currentAddress()).toBe(ON_THE_HIRE)
    await answer(user, COMPLETE)
    await user.click(screen.getByRole('button', { name: ASK }))
    network.setRoute(rentalRoute(), () => jsonResponse(SETTLED_AFTER_DAMAGE))
    const readsBefore = network.requestsTo(rentalRoute()).length
    await user.click(await screen.findByRole('button', { name: ANSWER }))

    await user.click(await screen.findByRole('link', { name: 'Back to the return of TSH-H-26-000099' }, SCREEN_WAIT))

    await findScreenHeading('Return and condition inspection')
    expect(await screen.findByText('TSH-H-26-000099 is settled', {}, SCREEN_WAIT)).toBeVisible()
    expect(network.requestsTo(rentalRoute()).length).toBeGreaterThan(readsBefore)
    expect(screen.queryByText('The deposit is waiting for a damage report')).not.toBeInTheDocument()
    expect(screen.getByText('The damage report is filed.')).toBeVisible()
    const charges = screen.getByRole('heading', { name: 'Charged against the deposit' }).parentElement
    if (charges === null) throw new Error('The charges against the deposit have no list around them.')
    expect(within(charges).getByText(/Damage to TSH-PC-0007/)).toBeVisible()
  })
})
