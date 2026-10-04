/**
 * Tests for the categories on SC-20, with the network replaced at `fetch`.
 *
 * The list in its states, adding a category with a parent chosen from the
 * top level only, changing one with only what changed, every 422 under its
 * field, and switching one off and on, each asked first with the server's
 * sentence shown on a 409 or a 403.
 */

import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createdResponse, jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  BREAKING,
  CATEGORIES_ROUTE,
  CREATE_CATEGORY_ROUTE,
  HAMMERS,
  WELDING,
  categoryList,
  categoryRoute,
} from '../../test/admin-catalogue-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { categoriesRegion, categoryRowOf, findCategories, lastBody, openCatalogue } from './SC20-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

function findForm(name: string): Promise<HTMLElement> {
  return screen.findByRole('form', { name }, SCREEN_WAIT)
}

async function addCategory(user: UserEvent): Promise<HTMLElement> {
  await findCategories()
  await user.click(within(categoriesRegion()).getByRole('button', { name: 'Add a category' }))
  return findForm('The new category')
}

describe('reading the categories', () => {
  it('lists every category with where it sits, its models and whether it is switched on', async () => {
    await openCatalogue()
    await findCategories()

    expect(within(categoriesRegion()).getByText(/^3 categories, switched on or off\./)).toBeVisible()
    const hammers = await categoryRowOf(HAMMERS.name)
    expect(within(hammers).getByText(HAMMERS.code)).toBeVisible()
    expect(within(hammers).getByText(BREAKING.name)).toBeVisible()
    expect(within(hammers).getByText('Switched on', { selector: '.pill' })).toBeVisible()
    const welding = await categoryRowOf(WELDING.name)
    expect(within(welding).getByText('Top level')).toBeVisible()
    expect(within(welding).getByText('Switched off', { selector: '.pill' })).toBeVisible()
    expect(within(welding).getByRole('button', { name: `Switch on ${WELDING.name}` })).toBeVisible()
  })

  it('draws a skeleton while they load', async () => {
    await openCatalogue({ [CATEGORIES_ROUTE]: neverAnswers })

    expect(await within(categoriesRegion()).findByText('Loading the categories.', {}, SCREEN_WAIT)).toBeInTheDocument()
  })

  it('says so when they cannot be read, and reads them again on a retry', async () => {
    const { user, network } = await openCatalogue({ [CATEGORIES_ROUTE]: () => problemResponse(500, { requestId: 'req-cat-1' }) })

    const alert = await within(categoriesRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the categories')
    network.setRoute(CATEGORIES_ROUTE, () => jsonResponse(categoryList()))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await categoryRowOf(BREAKING.name)).toBeVisible()
  })

  it('offers to add the first category when there are none', async () => {
    await openCatalogue({ [CATEGORIES_ROUTE]: () => jsonResponse(categoryList([])) })

    expect(await within(categoriesRegion()).findByText('There are no categories yet', {}, SCREEN_WAIT)).toBeVisible()
  })
})

describe('adding and changing a category', () => {
  it('offers only the top level categories as a parent', async () => {
    const { user } = await openCatalogue()
    const form = await addCategory(user)

    const parents = within(within(form).getByLabelText('Sits under')).getAllByRole('option').map((option) => option.textContent)
    expect(parents).toEqual(['Nothing, it is a top level category', BREAKING.name, `${WELDING.name} (switched off)`])
    expect(screen.getByRole('heading', { level: 3, name: 'Add a category' })).toHaveFocus()
  })

  it('asks first, then sends every field the route takes', async () => {
    const added = { ...HAMMERS, id: 'ca700000-0000-4000-8000-000000000009', code: 'BREAKER', name: 'Breakers', slug: 'breakers' }
    const { user, network } = await openCatalogue({ [CREATE_CATEGORY_ROUTE]: () => createdResponse(added) })
    const form = await addCategory(user)
    await user.type(within(form).getByLabelText('Name'), 'Breakers')
    await user.type(within(form).getByLabelText('Code'), 'BREAKER')
    await user.type(within(form).getByLabelText('Name in the web address'), 'breakers')
    await user.selectOptions(within(form).getByLabelText('Sits under'), BREAKING.id)

    await user.click(within(form).getByRole('button', { name: 'Add the category' }))
    expect(screen.getByRole('heading', { level: 3, name: 'Add Breakers to the categories?' })).toHaveFocus()
    expect(screen.getByText(`It sits under ${BREAKING.name}.`)).toBeVisible()
    expect(network.requestsTo(CREATE_CATEGORY_ROUTE)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Yes, add it' }))

    expect(await screen.findByText('Breakers is added to the categories', {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, CREATE_CATEGORY_ROUTE)).toEqual({
      code: 'BREAKER',
      name: 'Breakers',
      slug: 'breakers',
      description: null,
      parentCategoryId: BREAKING.id,
      sortOrder: 0,
    })
  })

  it('never offers a category as its own parent, and sends only what changed', async () => {
    const route = categoryRoute(BREAKING.id)
    const { user, network } = await openCatalogue({ [route]: () => jsonResponse({ ...BREAKING, sortOrder: 5 }) })
    await user.click(within(await categoryRowOf(BREAKING.name)).getByRole('button', { name: `Edit the category ${BREAKING.name}` }))
    const form = await findForm(`The details of ${BREAKING.name}`)

    const parents = within(within(form).getByLabelText('Sits under')).getAllByRole('option').map((option) => option.textContent)
    expect(parents).not.toContain(BREAKING.name)
    await user.clear(within(form).getByLabelText('Place in the list'))
    await user.type(within(form).getByLabelText('Place in the list'), '5')
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    expect(screen.getByText('The place in the list changes.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    await waitFor(() => expect(lastBody(network, route)).toEqual({ sortOrder: 5 }))
  })

  it.each([
    ['parentCategoryId', 'Sits under', 'This category has categories under it, so it has to stay at the top level.'],
    ['code', 'Code', 'That code is already in use.'],
  ])('puts a refusal of %s under its field', async (field, label, message) => {
    const route = categoryRoute(BREAKING.id)
    const { user } = await openCatalogue({ [route]: () => problemResponse(422, { errors: { fields: { [`body.${field}`]: message } } }) })
    await user.click(within(await categoryRowOf(BREAKING.name)).getByRole('button', { name: `Edit the category ${BREAKING.name}` }))
    const form = await findForm(`The details of ${BREAKING.name}`)
    await user.selectOptions(within(form).getByLabelText('Sits under'), WELDING.id)
    await user.click(within(form).getByRole('button', { name: 'Save the changes' }))
    await user.click(screen.getByRole('button', { name: 'Yes, save the changes' }))

    const control = await within(form).findByLabelText(label, {}, SCREEN_WAIT)
    await waitFor(() => expect(control).toHaveAccessibleDescription(expect.stringContaining(message)))
  })
})

describe('switching a category off and on', () => {
  it('asks first, then switches it off with one request and reads the list again', async () => {
    const route = categoryRoute(BREAKING.id)
    const { user, network } = await openCatalogue({ [route]: () => jsonResponse({ ...BREAKING, isActive: false }) })
    await user.click(within(await categoryRowOf(BREAKING.name)).getByRole('button', { name: `Switch off ${BREAKING.name}` }))

    expect(screen.getByRole('heading', { level: 3, name: `Switch ${BREAKING.name} off?` })).toHaveFocus()
    expect(screen.getByText(/Nothing is deleted/)).toBeVisible()
    const reads = network.requestsTo(CATEGORIES_ROUTE).length
    await user.click(screen.getByRole('button', { name: 'Yes, switch it off' }))

    expect(await screen.findByText(`${BREAKING.name} is switched off`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, route)).toEqual({ isActive: false })
    await waitFor(() => expect(network.requestsTo(CATEGORIES_ROUTE).length).toBeGreaterThan(reads))
  })

  it('switches one on again', async () => {
    const route = categoryRoute(WELDING.id)
    const { user, network } = await openCatalogue({ [route]: () => jsonResponse({ ...WELDING, isActive: true }) })
    await user.click(within(await categoryRowOf(WELDING.name)).getByRole('button', { name: `Switch on ${WELDING.name}` }))

    await user.click(screen.getByRole('button', { name: 'Yes, switch it on' }))

    expect(await screen.findByText(`${WELDING.name} is switched on`, {}, SCREEN_WAIT)).toBeVisible()
    expect(lastBody(network, route)).toEqual({ isActive: true })
  })

  it.each([
    [409, 'This category changed since the list was read.'],
    [403, 'Only the owner can change a category.'],
  ])('shows the server sentence for a %i', async (status, detail) => {
    const { user } = await openCatalogue({ [categoryRoute(BREAKING.id)]: () => problemResponse(status, { detail }) })
    await user.click(within(await categoryRowOf(BREAKING.name)).getByRole('button', { name: `Switch off ${BREAKING.name}` }))

    await user.click(screen.getByRole('button', { name: 'Yes, switch it off' }))

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('The category was not switched off')
    expect(alert).toHaveTextContent(detail)
  })

  it('puts the question away and gives focus back to its button', async () => {
    const { user } = await openCatalogue()
    await user.click(within(await categoryRowOf(BREAKING.name)).getByRole('button', { name: `Switch off ${BREAKING.name}` }))

    await user.click(screen.getByRole('button', { name: 'Keep it as it is' }))

    expect(screen.getByRole('button', { name: `Switch off ${BREAKING.name}` })).toHaveFocus()
  })
})
