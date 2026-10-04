/**
 * Tests for registering a unit on SC-21, with the network replaced at `fetch`.
 *
 * The form opens from the header, takes exactly the fields the route takes,
 * checks only what it needs to write a body, asks first, sends every field,
 * opens the new unit once the server has answered, puts every 422 under its
 * field with a cost in plain words, shows the server's sentence on a 409 or a
 * 403, and disables its answer while it is in flight.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { HAMMER, MODELS_ROUTE } from '../../test/admin-catalogue-samples'
import { INTAKE_UNIT, REGISTER_ROUTE, detailOf } from '../../test/admin-asset-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { REGISTER, findUnit, lastAsked, lastBody, openRegister } from './SC21-test-kit'

const ADDING = `${REGISTER}?add=unit`
const TAG = INTAKE_UNIT.assetTag

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

async function findForm(): Promise<HTMLElement> {
  return screen.findByRole('form', { name: 'The new unit' }, SCREEN_WAIT)
}

/** Search for the hammer and choose it. */
async function chooseTheHammer(user: UserEvent, form: HTMLElement): Promise<void> {
  await user.type(within(form).getByLabelText('Find the model by name or stock code'), 'gbh')
  const menu = within(form).getByLabelText('Model')
  await waitFor(() => expect(within(menu).getByRole('option', { name: `${HAMMER.name} (${HAMMER.sku})` })).toBeInTheDocument(), SCREEN_WAIT)
  await user.selectOptions(menu, HAMMER.id)
}

async function fill(user: UserEvent, form: HTMLElement): Promise<void> {
  await user.type(within(form).getByLabelText('Asset tag'), TAG)
  await chooseTheHammer(user, form)
  await user.selectOptions(within(form).getByLabelText('Branch it belongs to'), 'CBD')
  await user.type(within(form).getByLabelText('Bought on'), '2026-03-10')
  await user.type(within(form).getByLabelText('Cost, in rand'), '3980')
  await user.type(within(form).getByLabelText('Serial number'), 'GBH-112233')
  await user.selectOptions(within(form).getByLabelText('Condition grade'), 'B')
  await user.type(within(form).getByLabelText('Meter reading, in hours'), '12')
  await user.type(within(form).getByLabelText('Notes'), 'Bought with a spare chuck.')
}

describe('registering a unit', () => {
  it('opens from the header with its heading in focus', async () => {
    const { user } = await openRegister()

    await user.click(screen.getAllByRole('button', { name: 'Register a unit' })[0])

    await waitFor(() => expect(currentAddress()).toBe(ADDING))
    expect(await screen.findByRole('heading', { level: 2, name: 'Register a unit' }, SCREEN_WAIT)).toHaveFocus()
  })

  it('asks for a model, a branch and a day before anything is sent', async () => {
    const { user, network } = await openRegister({}, ADDING)
    const form = await findForm()

    await user.click(within(form).getByRole('button', { name: 'Register the unit' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has been saved yet. 3 answers need fixing.')
    expect(within(form).getByLabelText('Model')).toHaveAccessibleDescription(expect.stringContaining('Choose the model this unit is.'))
    expect(within(form).getByLabelText('Branch it belongs to')).toHaveAccessibleDescription('Choose the branch the unit belongs to.')
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(0)
  })

  it('asks first, sends exactly the fields of the route, and opens the new unit', async () => {
    const { user, network } = await openRegister({ [REGISTER_ROUTE]: () => createdResponse(detailOf(INTAKE_UNIT, [])) }, ADDING)
    const form = await findForm()
    await fill(user, form)
    expect(lastAsked(network, MODELS_ROUTE).get('q')).toBe('gbh')

    await user.click(within(form).getByRole('button', { name: 'Register the unit' }))
    expect(screen.getByRole('heading', { level: 3, name: `Register ${TAG}?` })).toHaveFocus()
    expect(screen.getByText(/It starts at intake, so nobody can book it/)).toBeVisible()
    expect(screen.getByText(`They are ${TAG}, ${HAMMER.name} and Cape Town CBD.`, { exact: false })).toBeVisible()
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, register it' }))

    expect(await screen.findByText(`${TAG} is registered at intake`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, REGISTER_ROUTE)).toEqual({
      assetTag: TAG,
      modelId: HAMMER.id,
      branchCode: 'CBD',
      serialNumber: 'GBH-112233',
      conditionGrade: 'B',
      acquiredOn: '2026-03-10',
      acquisitionCost: '3980.00',
      hourMeterReading: 12,
      notes: 'Bought with a spare chuck.',
    })
    await waitFor(() => expect(currentAddress()).toBe(`${REGISTER}?asset=${TAG}`))
    expect(await findUnit(TAG)).toBeVisible()
  })

  it('puts a tag in use under the tag and a cost it cannot read in plain words', async () => {
    const pattern = "String should match pattern '^-?\\d{1,10}(\\.\\d{1,2})?$'"
    const refusal = () =>
      problemResponse(422, {
        errors: { fields: { 'body.assetTag': 'Another unit already carries that tag.', 'body.acquisitionCost': pattern } },
      })
    const { user, network } = await openRegister({ [REGISTER_ROUTE]: refusal }, ADDING)
    const form = await findForm()
    await fill(user, form)
    await user.clear(within(form).getByLabelText('Cost, in rand'))
    await user.type(within(form).getByLabelText('Cost, in rand'), 'about 4000')
    await user.click(within(form).getByRole('button', { name: 'Register the unit' }))
    await user.click(screen.getByRole('button', { name: 'Yes, register it' }))

    const tag = await within(form).findByLabelText('Asset tag', {}, SCREEN_WAIT)
    await waitFor(() => expect(tag).toHaveAccessibleDescription(expect.stringContaining('Another unit already carries that tag.')))
    const plain = 'Enter an amount in rand, for example 280.00.'
    const problems = screen.getByRole('alert')
    expect(within(problems).getByRole('link', { name: plain })).toHaveAttribute('href', '#asset-acquisitionCost')
    expect(screen.queryByText(/should match pattern/)).not.toBeInTheDocument()
    expect(lastBody(network, REGISTER_ROUTE)).toEqual(expect.objectContaining({ acquisitionCost: 'about 4000' }))
  })

  it.each([
    [409, 'That unit was registered a moment ago at another desk.'],
    [403, 'Only the owner can register a unit.'],
  ])('shows the server sentence for a %i in the question', async (status, detail) => {
    const { user } = await openRegister({ [REGISTER_ROUTE]: () => problemResponse(status, { detail }) }, ADDING)
    const form = await findForm()
    await fill(user, form)
    await user.click(within(form).getByRole('button', { name: 'Register the unit' }))

    await user.click(screen.getByRole('button', { name: 'Yes, register it' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The unit was not registered')
    expect(alert).toHaveTextContent(detail)
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openRegister({ [REGISTER_ROUTE]: neverAnswers }, ADDING)
    const form = await findForm()
    await fill(user, form)
    await user.click(within(form).getByRole('button', { name: 'Register the unit' }))

    await user.click(screen.getByRole('button', { name: 'Yes, register it' }))

    const waiting = await screen.findByRole('button', { name: 'Registering it' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(1)
  })

  it('closes unsaved and gives focus back to the button that opened it', async () => {
    const { user } = await openRegister({}, ADDING)
    const form = await findForm()

    await user.click(within(form).getByRole('button', { name: 'Close the form' }))

    await waitFor(() => expect(currentAddress()).toBe(REGISTER))
    expect(screen.getAllByRole('button', { name: 'Register a unit' })[0]).toHaveFocus()
  })
})
