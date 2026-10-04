/**
 * Tests for changing and adding a model on SC-20, with the network replaced
 * at `fetch`.
 *
 * A change opens from the model's own read, shows the stock code read only,
 * asks first and says that bookings already made keep their rate before a
 * figure moves, and sends only what changed. A new model sends every field the
 * route takes. Every 422 lands under its field, a 409 or a 403 shows the
 * server's sentence, the answer is disabled while it is in flight, and the
 * list is read again once the server has answered.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money } from '../../shared/format'
import { createdResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  CREATE_MODEL_ROUTE,
  HAMMER,
  HAMMERS,
  MODELS_ROUTE,
  modelRoute,
} from '../../test/admin-catalogue-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { BOOKINGS_KEEP_THEIR_RATE } from './SC20-Model-Save-Question'
import { lastBody, openCatalogue, rowOf } from './SC20-test-kit'

const CATALOGUE = '/admin/catalogue'
const EDITING = `${CATALOGUE}?model=${HAMMER.id}`
const CHANGE_ROUTE = modelRoute(HAMMER.id, 'PATCH')

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Wait for the form of a model to be open with its fields. */
async function findForm(name: string): Promise<HTMLElement> {
  return screen.findByRole('form', { name }, SCREEN_WAIT)
}

async function retype(user: UserEvent, field: HTMLElement, value: string): Promise<void> {
  await user.clear(field)
  await user.type(field, value)
}

describe('changing a model', () => {
  it('opens from the list, reads the model by its own route and shows the stock code read only', async () => {
    const { user, network } = await openCatalogue()
    await user.click(within(await rowOf(HAMMER.name)).getByRole('button', { name: `Edit ${HAMMER.name}` }))

    const form = await findForm(`The details of ${HAMMER.name}`)
    expect(screen.getByRole('heading', { level: 2, name: `Change ${HAMMER.name}` })).toHaveFocus()
    expect(currentAddress()).toBe(EDITING)
    expect(network.requestsTo(modelRoute(HAMMER.id))).toHaveLength(1)
    expect(within(form).queryByRole('textbox', { name: 'Stock code' })).not.toBeInTheDocument()
    expect(within(form).getByText(HAMMER.sku)).toBeVisible()
    expect(within(form).getByLabelText('Late fee per day, in rand')).toHaveValue(HAMMER.lateFeePerDay)
    expect(within(form).getByLabelText('Category it sits in')).toHaveValue(HAMMERS.id)
  })

  it('says that bookings keep their rate before saving a new figure, then sends only that figure', async () => {
    const saved = { ...HAMMER, lateFeePerDay: '51.00' }
    const { user, network } = await openCatalogue({ [CHANGE_ROUTE]: () => jsonResponse(saved) }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Late fee per day, in rand'), '51')

    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByRole('heading', { level: 3, name: `Save the changes to ${HAMMER.name}?` })).toHaveFocus()
    expect(screen.getByText(`The late fee per day goes from ${money('50.00')} to ${money('51.00')}.`)).toBeVisible()
    expect(screen.getByText(BOOKINGS_KEEP_THEIR_RATE)).toBeVisible()
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(0)
    const listReads = network.requestsTo(MODELS_ROUTE).length

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    expect(await screen.findByText(`${HAMMER.name} is saved`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, CHANGE_ROUTE)).toEqual({ lateFeePerDay: '51.00' })
    expect(screen.getByText(/New bookings take the new figures/)).toBeVisible()
    await waitFor(() => expect(currentAddress()).toBe(CATALOGUE))
    await waitFor(() => expect(network.requestsTo(MODELS_ROUTE).length).toBeGreaterThan(listReads))
  })

  it('says nothing about bookings when no figure moves', async () => {
    const { user, network } = await openCatalogue({ [CHANGE_ROUTE]: () => jsonResponse({ ...HAMMER, name: 'GBH 2-26' }) }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Name'), 'GBH 2-26')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByText('The name changes.')).toBeVisible()
    expect(screen.queryByText(BOOKINGS_KEEP_THEIR_RATE)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    await waitFor(() => expect(lastBody(network, CHANGE_ROUTE)).toEqual({ name: 'GBH 2-26' }))
  })

  it('sends nothing when nothing changed', async () => {
    const { user, network } = await openCatalogue({}, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)

    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    expect(screen.getByText('Nothing has changed yet')).toBeVisible()
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(0)
  })

  it('goes back to the form with each refusal under its field, and lists one with no field', async () => {
    const refusal = () =>
      problemResponse(422, {
        errors: {
          fields: {
            'body.weeklyRate': 'The weekly rate cannot be more than seven days at the daily rate.',
            'body.isPublished': 'Publish a model from the list.',
          },
        },
      })
    const { user } = await openCatalogue({ [CHANGE_ROUTE]: refusal }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Weekly rate, in rand'), '9999')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const weekly = await within(form).findByLabelText('Weekly rate, in rand', {}, SCREEN_WAIT)
    await waitFor(() =>
      expect(weekly).toHaveAccessibleDescription(expect.stringContaining('The weekly rate cannot be more than seven days')),
    )
    expect(weekly).toBeEnabled()
    const problems = screen.getByRole('alert')
    expect(problems).toHaveTextContent('Nothing has been saved yet. 2 answers need fixing.')
    expect(within(problems).getByRole('link', { name: /The weekly rate cannot be more/ })).toHaveAttribute('href', '#model-weeklyRate')
    expect(problems).toHaveTextContent('Publish a model from the list.')
    expect(problems.parentElement).toHaveFocus()
  })

  it.each([
    [409, 'The model changed since you opened it. Open it again.'],
    [403, 'Only the owner can change the catalogue.'],
  ])('shows the server sentence for a %i in the question', async (status, detail) => {
    const { user } = await openCatalogue({ [CHANGE_ROUTE]: () => problemResponse(status, { detail }) }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Daily rate, in rand'), '300')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The changes were not saved')
    expect(alert).toHaveTextContent(detail)
  })

  it('disables the answer while the request is in flight, so it is sent once', async () => {
    const { user, network } = await openCatalogue({ [CHANGE_ROUTE]: neverAnswers }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Deposit, in rand'), '1600')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))

    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const waiting = await screen.findByRole('button', { name: 'Saving the changes' })
    expect(waiting).toBeDisabled()
    await user.click(waiting)
    expect(network.requestsTo(CHANGE_ROUTE)).toHaveLength(1)
  })

  it.each([
    ['a key it does not know', () => problemResponse(404)],
    ['something that is not a key', () => problemResponse(422, { errors: { fields: { 'path.id': 'Input should be a valid UUID' } } })],
  ])('says so plainly for %s', async (_what, answer) => {
    await openCatalogue({ [modelRoute(HAMMER.id)]: answer }, EDITING)

    expect(await screen.findByRole('heading', { level: 2, name: 'That model is not in the catalogue' }, SCREEN_WAIT)).toBeVisible()
  })

  it('puts a figure the server could not read as an amount in plain words, linked to its box', async () => {
    const pattern = "String should match pattern '^-?\\d{1,10}(\\.\\d{1,2})?$'"
    const refusal = () => problemResponse(422, { errors: { fields: { 'body.dailyRate': pattern } } })
    const { user, network } = await openCatalogue({ [CHANGE_ROUTE]: refusal }, EDITING)
    const form = await findForm(`The details of ${HAMMER.name}`)
    await retype(user, within(form).getByLabelText('Daily rate, in rand'), 'about 300')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const problems = await screen.findByRole('alert', {}, SCREEN_WAIT)
    const plain = 'Enter an amount in rand, for example 280.00.'
    expect(within(problems).getByRole('link', { name: plain })).toHaveAttribute('href', '#model-dailyRate')
    expect(within(form).getByLabelText('Daily rate, in rand')).toHaveAccessibleDescription(expect.stringContaining(plain))
    expect(screen.queryByText(/should match pattern/)).not.toBeInTheDocument()
    expect(lastBody(network, CHANGE_ROUTE)).toEqual({ dailyRate: 'about 300' })
  })

  it('closes unsaved and gives focus back to the button that opened it', async () => {
    const { user } = await openCatalogue()
    await user.click(within(await rowOf(HAMMER.name)).getByRole('button', { name: `Edit ${HAMMER.name}` }))
    const form = await findForm(`The details of ${HAMMER.name}`)

    await user.click(within(form).getByRole('button', { name: 'Close the form' }))

    await waitFor(() => expect(currentAddress()).toBe(CATALOGUE))
    expect(screen.getByRole('button', { name: `Edit ${HAMMER.name}` })).toHaveFocus()
  })
})

describe('adding a model', () => {
  const ADDED = { ...HAMMER, id: 'a0de1000-0000-4000-8000-000000000099', sku: 'DR-MAKITA-HR2470', name: 'Makita HR2470', isPublished: false, assetCount: 0 }

  async function fill(user: UserEvent, form: HTMLElement): Promise<void> {
    const values: [string, string][] = [
      ['Stock code', ADDED.sku],
      ['Name', ADDED.name],
      ['Name in the web address', 'hr2470-rotary-hammer'],
      ['Manufacturer', 'Makita'],
      ['Model number', 'HR2470'],
      ['Short description', 'Light SDS-plus hammer.'],
      ['Daily rate, in rand', '240'],
      ['Weekly rate, in rand', '960.5'],
      ['Deposit, in rand', '1200.00'],
      ['Late fee per day, in rand', '40'],
      ['Replacement value, in rand', '3600'],
      ['Shortest hire, in days', '1'],
      ['Longest hire, in days', '28'],
    ]
    for (const [label, value] of values) await user.type(within(form).getByLabelText(label), value)
    await user.selectOptions(within(form).getByLabelText('Category it sits in'), HAMMERS.id)
  }

  it('asks for a category and whole days before anything is sent', async () => {
    const { user, network } = await openCatalogue({}, `${CATALOGUE}?model=new`)
    const form = await findForm('The new model')

    await user.click(within(form).getByRole('button', { name: 'Add the model' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Nothing has been saved yet. 3 answers need fixing.')
    expect(within(form).getByLabelText('Category it sits in')).toHaveAccessibleDescription('Choose the category the model sits in.')
    expect(network.requestsTo(CREATE_MODEL_ROUTE)).toHaveLength(0)
  })

  it('asks first, then sends every field the route takes and shows the new model in the list', async () => {
    const { user, network } = await openCatalogue({ [CREATE_MODEL_ROUTE]: () => createdResponse(ADDED) }, `${CATALOGUE}?model=new`)
    expect(await screen.findByRole('heading', { level: 2, name: 'Add a model' }, SCREEN_WAIT)).toHaveFocus()
    const form = await findForm('The new model')
    await fill(user, form)

    await user.click(within(form).getByRole('button', { name: 'Add the model' }))
    expect(screen.getByRole('heading', { level: 3, name: `Add ${ADDED.name} to the catalogue?` })).toHaveFocus()
    expect(screen.getByText(/hidden from customers/)).toBeVisible()
    expect(network.requestsTo(CREATE_MODEL_ROUTE)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, add it' }))

    expect(await screen.findByText(`${ADDED.name} is in the catalogue`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, CREATE_MODEL_ROUTE)).toEqual({
      sku: ADDED.sku,
      name: ADDED.name,
      slug: 'hr2470-rotary-hammer',
      categoryId: HAMMERS.id,
      manufacturer: 'Makita',
      modelNumber: 'HR2470',
      shortDescription: 'Light SDS-plus hammer.',
      longDescription: null,
      dailyRate: '240.00',
      weeklyRate: '960.50',
      depositAmount: '1200.00',
      lateFeePerDay: '40.00',
      replacementValue: '3600.00',
      minHireDays: 1,
      maxHireDays: 28,
    })
    await waitFor(() => expect(currentAddress()).toBe(`${CATALOGUE}?q=${ADDED.sku}`))
  })

  it('puts a duplicate stock code under the stock code', async () => {
    const { user } = await openCatalogue(
      { [CREATE_MODEL_ROUTE]: () => problemResponse(422, { errors: { fields: { 'body.sku': 'That stock code is already in use.' } } }) },
      `${CATALOGUE}?model=new`,
    )
    const form = await findForm('The new model')
    await fill(user, form)
    await user.click(within(form).getByRole('button', { name: 'Add the model' }))
    await user.click(screen.getByRole('button', { name: 'Yes, add it' }))

    const sku = await within(form).findByRole('textbox', { name: 'Stock code' }, SCREEN_WAIT)
    await waitFor(() => expect(sku).toHaveAccessibleDescription(expect.stringContaining('That stock code is already in use.')))
  })
})
