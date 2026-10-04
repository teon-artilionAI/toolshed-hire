/**
 * Tests for one unit on SC-21 and the change of its paperwork, with the
 * network replaced at `fetch`.
 *
 * A unit opens from the list by its own read, shows every field the server
 * sent, links its open damage reports and every booking, hire and report of
 * its history to the screen where each is dealt with, and has the shared
 * loading, failed and not found states. A change of its paperwork shows the
 * tag, the model and the branch read only, asks first, sends only what
 * changed, puts every 422 under its field, shows the server's sentence on a
 * 409 or a 403, and reads the register again once the server has answered.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { formatDate, money } from '../../shared/format'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  ASSETS_ROUTE,
  BOOKING_REFERENCE,
  HIRE_REFERENCE,
  REPORT_REFERENCE,
  SHELF_UNIT,
  assetRoute,
  detailOf,
} from '../../test/admin-asset-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { REGISTER, findUnit, lastBody, openRegister, rowOf } from './SC21-test-kit'

const TAG = SHELF_UNIT.assetTag
const OPEN = `${REGISTER}?asset=${TAG}`
const CHANGE_ROUTE = assetRoute(TAG, 'PATCH')

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function retype(user: UserEvent, field: HTMLElement, value: string): Promise<void> {
  await user.clear(field)
  if (value !== '') await user.type(field, value)
}

describe('one unit', () => {
  it('opens from the list by its own read, with every field the server sent', async () => {
    const { user, network } = await openRegister()
    await user.click(within(await rowOf(TAG)).getByRole('link', { name: `Open ${TAG}` }))

    const unit = await findUnit(TAG)
    expect(screen.getByRole('heading', { level: 2, name: `Unit ${TAG}` })).toHaveFocus()
    expect(currentAddress()).toBe(OPEN)
    expect(network.requestsTo(assetRoute(TAG))).toHaveLength(1)
    expect(within(unit).getByText('GBH-778812')).toBeVisible()
    expect(within(unit).getByText('On the shelf', { selector: '.pill' })).toBeVisible()
    expect(within(unit).getByText('B, good working order')).toBeVisible()
    expect(within(unit).getByText(`${formatDate(SHELF_UNIT.acquiredOn)} for`, { exact: false })).toHaveTextContent(
      money(SHELF_UNIT.acquisitionCost),
    )
    expect(within(unit).getByText('412 hours')).toBeVisible()
    expect(within(unit).getByText('1 booking')).toBeVisible()
    expect(within(unit).getByText(SHELF_UNIT.notes ?? '')).toBeVisible()
    expect(within(unit).getByRole('link', { name: /^2 open damage reports, resolve on the damage screen/ })).toHaveAttribute(
      'href',
      `/counter/damage/${TAG}`,
    )
  })

  it('lists its history, newest first, each booking, hire and report a link to where it is dealt with', async () => {
    await openRegister({}, OPEN)
    const unit = await findUnit(TAG)

    const history = within(unit).getByRole('list', { name: `The history of ${TAG}` })
    const entries = within(history).getAllByRole('listitem')
    expect(entries).toHaveLength(4)
    expect(entries[0]).toHaveTextContent(`Held for booking ${BOOKING_REFERENCE}`)
    expect(within(history).getByRole('link', { name: `Open booking ${BOOKING_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/checkout/${BOOKING_REFERENCE}`,
    )
    expect(within(history).getByRole('link', { name: `Open hire ${HIRE_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/return/${HIRE_REFERENCE}`,
    )
    expect(within(history).getByRole('link', { name: `Open damage report ${REPORT_REFERENCE}` })).toHaveAttribute(
      'href',
      `/counter/damage/${TAG}`,
    )
    expect(entries[3]).toHaveTextContent('Registered in the fleet at INTAKE.')
    expect(within(unit).getByRole('link', { name: `Open the events of ${TAG} in the audit trail` })).toHaveAttribute(
      'href',
      `/admin/audit?entityType=asset&entityId=${SHELF_UNIT.id}`,
    )
  })

  it('draws a skeleton while it loads', async () => {
    await openRegister({ [assetRoute(TAG)]: neverAnswers }, OPEN)

    expect(await screen.findByText('Loading the unit.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: `Opening unit ${TAG}` })).toBeVisible()
  })

  it('says so when it cannot be read, and reads it again on a retry', async () => {
    const { user, network } = await openRegister({ [assetRoute(TAG)]: () => problemResponse(500) }, OPEN)

    expect(await screen.findByText('We could not load the unit', {}, SCREEN_WAIT)).toBeVisible()
    network.setRoute(assetRoute(TAG), () => jsonResponse(detailOf(SHELF_UNIT)))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await findUnit(TAG)).toBeVisible()
  })

  it('says plainly that no unit carries a tag the server does not know', async () => {
    await openRegister({ [assetRoute('TSH-XX-9999')]: () => problemResponse(404) }, `${REGISTER}?asset=TSH-XX-9999`)

    expect(await screen.findByRole('heading', { level: 2, name: 'That unit is not on the register' }, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByText('No unit carries the tag TSH-XX-9999')).toBeVisible()
  })

  it('closes and gives focus back to the link that opened it', async () => {
    const { user } = await openRegister()
    await user.click(within(await rowOf(TAG)).getByRole('link', { name: `Open ${TAG}` }))
    const unit = await findUnit(TAG)

    await user.click(within(unit).getByRole('button', { name: 'Close the unit' }))

    await waitFor(() => expect(currentAddress()).toBe(REGISTER))
    await waitFor(() => expect(screen.getByRole('link', { name: `Open ${TAG}` })).toHaveFocus())
  })
})

describe('changing the paperwork', () => {
  async function openTheForm(routes = {}): Promise<{ user: UserEvent; form: HTMLElement; network: Awaited<ReturnType<typeof openRegister>>['network'] }> {
    const { user, network } = await openRegister(routes, OPEN)
    const unit = await findUnit(TAG)
    await user.click(within(unit).getByRole('button', { name: 'Change the serial number, grade, meter reading or notes' }))
    const form = await screen.findByRole('form', { name: `The details of ${TAG}` }, SCREEN_WAIT)
    return { user, form, network }
  }

  it('shows the tag, model and branch read only, asks first, and sends only what changed', async () => {
    const saved = detailOf({ ...SHELF_UNIT, serialNumber: 'GBH-990001', notes: null })
    const { user, form, network } = await openTheForm({ [CHANGE_ROUTE]: () => jsonResponse(saved) })
    expect(within(form).getByText('The tag, the model and the branch never change once a unit is registered.')).toBeVisible()
    expect(within(form).queryByRole('textbox', { name: /tag/i })).not.toBeInTheDocument()
    await retype(user, within(form).getByLabelText('Serial number'), 'GBH-990001')
    await retype(user, within(form).getByLabelText('Notes'), '')
    const listReads = network.requestsTo(ASSETS_ROUTE).length

    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    expect(screen.getByRole('heading', { level: 4, name: `Save the changes to ${TAG}?` })).toHaveFocus()
    expect(screen.getByText('The serial number and the notes change.')).toBeVisible()
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    expect(await screen.findByText(`The details of ${TAG} are saved`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, CHANGE_ROUTE)).toEqual({ serialNumber: 'GBH-990001', notes: null })
    await waitFor(() => expect(network.requestsTo(ASSETS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('sends nothing when nothing changed', async () => {
    const { user, form, network } = await openTheForm()

    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByText('Nothing has changed yet')).toBeVisible()
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(0)
  })

  it('asks for a whole number of hours before anything is sent', async () => {
    const { user, form, network } = await openTheForm()
    await retype(user, within(form).getByLabelText('Meter reading, in hours'), 'about 400')

    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has been saved yet. 1 answer needs fixing.')
    expect(within(form).getByLabelText('Meter reading, in hours')).toHaveAccessibleDescription(
      expect.stringContaining('whole number'),
    )
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(0)
  })

  it('goes back to the form with each refusal under its field, and lists one with no field', async () => {
    const refusal = () =>
      problemResponse(422, {
        errors: { fields: { 'body.hourMeterReading': 'Enter a meter reading of zero hours or more.', 'body.assetTag': 'The tag never changes.' } },
      })
    const { user, form } = await openTheForm({ [CHANGE_ROUTE]: refusal })
    await retype(user, within(form).getByLabelText('Meter reading, in hours'), '-4')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const meter = await within(form).findByLabelText('Meter reading, in hours', {}, SCREEN_WAIT)
    await waitFor(() => expect(meter).toHaveAccessibleDescription(expect.stringContaining('zero hours or more')))
    const problems = screen.getByRole('alert')
    expect(problems).toHaveTextContent('Nothing has been saved yet. 2 answers need fixing.')
    expect(within(problems).getByRole('link', { name: /zero hours or more/ })).toHaveAttribute('href', '#asset-hourMeterReading')
    expect(problems).toHaveTextContent('The tag never changes.')
  })

  it.each([
    [409, 'The unit changed since you opened it. Open it again.'],
    [403, 'Only the owner can change the register.'],
  ])('shows the server sentence for a %i in the question', async (status, detail) => {
    const { user, form } = await openTheForm({ [CHANGE_ROUTE]: () => problemResponse(status, { detail }) })
    await user.selectOptions(within(form).getByLabelText('Condition grade'), 'C')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The changes were not saved')
    expect(alert).toHaveTextContent(detail)
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, form, network } = await openTheForm({ [CHANGE_ROUTE]: neverAnswers })
    await retype(user, within(form).getByLabelText('Meter reading, in hours'), '500')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const waiting = await screen.findByRole('button', { name: 'Saving the changes' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(1)
    expect(lastBody(network, CHANGE_ROUTE)).toEqual({ hourMeterReading: 500 })
  })
})
