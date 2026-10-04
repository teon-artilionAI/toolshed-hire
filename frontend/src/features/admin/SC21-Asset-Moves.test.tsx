/**
 * Tests for the moves of a unit through its lifecycle on SC-21, with the
 * network replaced at `fetch`.
 *
 * The buttons are exactly the server's `allowedTransitions`, in words. Each
 * move asks first, asks why where the contract asks for a reason, sends the
 * status and the reason, disables its answer while in flight, shows the
 * server's sentence on a 409 with the booking it names as a link, shows a 403,
 * puts a refused reason under its box, and reads the register again.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  ASSETS_ROUTE,
  BOOKING_REFERENCE,
  INTAKE_UNIT,
  RETIRED_UNIT,
  SHELF_UNIT,
  assetRoute,
  detailOf,
  moveRoute,
} from '../../test/admin-asset-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { REGISTER, findUnit, lastBody, openRegister } from './SC21-test-kit'

const REASON = 'Gearbox grinding under load.'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function movesOf(unit: HTMLElement): HTMLElement {
  return within(unit).getByRole('region', { name: 'Move it through its life' })
}

describe('the moves a unit offers', () => {
  it('offers exactly what the server allows from intake, in words', async () => {
    await openRegister({}, `${REGISTER}?asset=${INTAKE_UNIT.assetTag}`)
    const moves = movesOf(await findUnit(INTAKE_UNIT.assetTag))

    expect(within(moves).getAllByRole('button').map((button) => button.textContent)).toEqual(['Commission it', 'Quarantine it'])
  })

  it('offers exactly what the server allows from the shelf, in words', async () => {
    await openRegister({}, `${REGISTER}?asset=${SHELF_UNIT.assetTag}`)
    const moves = movesOf(await findUnit(SHELF_UNIT.assetTag))

    expect(within(moves).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Quarantine it',
      'Send it for repair',
      'Retire it',
    ])
  })

  it('says so when the server offers no move', async () => {
    await openRegister({}, `${REGISTER}?asset=${RETIRED_UNIT.assetTag}`)
    const moves = movesOf(await findUnit(RETIRED_UNIT.assetTag))

    expect(within(moves).queryByRole('button')).not.toBeInTheDocument()
    expect(moves).toHaveTextContent('There is no move to make by hand from where this unit stands.')
  })
})

describe('making a move', () => {
  const TAG = INTAKE_UNIT.assetTag
  const AT = `${REGISTER}?asset=${TAG}`
  const commissioned = detailOf({ ...INTAKE_UNIT, status: 'AVAILABLE', allowedTransitions: ['QUARANTINED', 'UNDER_REPAIR', 'RETIRED'] })

  it('asks first, sends the status alone when no reason is asked, and shows the unit as it now stands', async () => {
    // The unit's own read answers as the server would, before the move and after it.
    let stored = detailOf(INTAKE_UNIT, [])
    const { user, network } = await openRegister(
      {
        [assetRoute(TAG)]: () => jsonResponse(stored),
        [moveRoute(TAG)]: () => {
          stored = commissioned
          return jsonResponse(commissioned)
        },
      },
      AT,
    )
    const unit = await findUnit(TAG)
    const listReads = network.requestsTo(ASSETS_ROUTE).length

    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Commission it' }))
    expect(screen.getByRole('heading', { level: 4, name: `Commission ${TAG}?` })).toHaveFocus()
    expect(screen.getByText(/It goes on the shelf at Cape Town CBD/)).toBeVisible()
    expect(within(unit).queryByLabelText('Why')).not.toBeInTheDocument()
    expect(network.requestsTo(moveRoute(TAG))).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, commission it' }))

    const outcome = await screen.findByText(`${TAG} is now on the shelf`, {}, SCREEN_WAIT)
    expect(outcome.closest('[tabindex="-1"]')).toHaveFocus()
    expect(lastBody(network, moveRoute(TAG))).toEqual({ to: 'AVAILABLE' })
    await waitFor(() => expect(within(movesOf(unit)).getByRole('button', { name: 'Retire it' })).toBeVisible())
    await waitFor(() => expect(network.requestsTo(ASSETS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('asks why before a unit is retired, says its row and history are kept, and sends the reason', async () => {
    const retired = detailOf({ ...SHELF_UNIT, status: 'RETIRED', retiredOn: '2026-03-12', allowedTransitions: [] })
    const tag = SHELF_UNIT.assetTag
    const { user, network } = await openRegister({ [moveRoute(tag)]: () => jsonResponse(retired) }, `${REGISTER}?asset=${tag}`)
    const unit = await findUnit(tag)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Retire it' }))

    expect(screen.getByText(/Its row and its whole history are kept, because nothing is ever deleted\./)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, retire it' }))
    expect(within(unit).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('Write the reason'))
    expect(network.requestsTo(moveRoute(tag))).toHaveLength(0)

    await user.type(within(unit).getByLabelText('Why'), REASON)
    await user.click(screen.getByRole('button', { name: 'Yes, retire it' }))

    expect(await screen.findByText(`${tag} is retired`, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText(/Its row and its whole history stay on the register\./)).toBeVisible()
    expect(lastBody(network, moveRoute(tag))).toEqual({ to: 'RETIRED', reason: REASON })
  })

  it('shows the sentence of a 409 with the booking it names as a link to its checkout', async () => {
    const tag = SHELF_UNIT.assetTag
    const detail = `Unit ${tag} is held for booking ${BOOKING_REFERENCE}, so it cannot be retired. Release it from that booking first.`
    const { user } = await openRegister({ [moveRoute(tag)]: () => problemResponse(409, { detail }) }, `${REGISTER}?asset=${tag}`)
    const unit = await findUnit(tag)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Retire it' }))
    await user.type(within(unit).getByLabelText('Why'), REASON)

    await user.click(screen.getByRole('button', { name: 'Yes, retire it' }))

    const alert = await within(unit).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent(`${tag} was not moved`)
    expect(alert).toHaveTextContent(detail)
    expect(within(alert).getByRole('link', { name: BOOKING_REFERENCE })).toHaveAttribute('href', `/counter/checkout/${BOOKING_REFERENCE}`)
  })

  it('shows the sentence of a 403', async () => {
    const detail = 'Only an administrator may move a unit.'
    const { user } = await openRegister({ [moveRoute(TAG)]: () => problemResponse(403, { detail }) }, AT)
    const unit = await findUnit(TAG)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Commission it' }))

    await user.click(screen.getByRole('button', { name: 'Yes, commission it' }))

    expect(await within(unit).findByRole('alert', {}, SCREEN_WAIT)).toHaveTextContent(detail)
  })

  it('puts a refused reason under its box', async () => {
    const refusal = () =>
      problemResponse(422, { errors: { fields: { 'body.reason': 'Say why the unit is being put in quarantine, in 5 to 200 characters.' } } })
    const { user } = await openRegister({ [moveRoute(TAG)]: refusal }, AT)
    const unit = await findUnit(TAG)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Quarantine it' }))
    await user.type(within(unit).getByLabelText('Why'), 'Smells of burning.')

    await user.click(screen.getByRole('button', { name: 'Yes, quarantine it' }))

    await waitFor(() =>
      expect(within(unit).getByLabelText('Why')).toHaveAccessibleDescription(expect.stringContaining('in 5 to 200 characters')),
    )
    expect(within(unit).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openRegister({ [moveRoute(TAG)]: neverAnswers }, AT)
    const unit = await findUnit(TAG)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Quarantine it' }))
    await user.type(within(unit).getByLabelText('Why'), 'Smells of burning.')

    await user.click(screen.getByRole('button', { name: 'Yes, quarantine it' }))

    const waiting = await screen.findByRole('button', { name: 'Quarantining it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(moveRoute(TAG))).toHaveLength(1)
    expect(lastBody(network, moveRoute(TAG))).toEqual({ to: 'QUARANTINED', reason: 'Smells of burning.' })
  })

  it('puts the question away unanswered and gives focus back to its button', async () => {
    const { user, network } = await openRegister({}, AT)
    const unit = await findUnit(TAG)
    await user.click(within(movesOf(unit)).getByRole('button', { name: 'Quarantine it' }))

    await user.click(screen.getByRole('button', { name: 'Keep it as it is' }))

    await waitFor(() => expect(within(movesOf(unit)).getByRole('button', { name: 'Quarantine it' })).toHaveFocus())
    expect(network.requestsTo(moveRoute(TAG))).toHaveLength(0)
  })
})
