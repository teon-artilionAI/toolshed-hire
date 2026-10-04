/**
 * Tests for the list of models on SC-20, with the network replaced at `fetch`.
 *
 * The list is one paged read with a search and two filters. Waiting, failed,
 * empty and loaded, every figure as the server sent it, the search and the
 * filters in the address and in the query, a refusal under its control, and
 * paging.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { money } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  BREAKER,
  CATEGORIES_ROUTE,
  HAMMER,
  HAMMERS,
  MODELS_ROUTE,
  modelPage,
} from '../../test/admin-catalogue-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { findModels, lastAsked, modelsRegion, openCatalogue, rowOf } from './SC20-test-kit'

const CATALOGUE = '/admin/catalogue'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('reading the models', () => {
  it('is connected, and shows every model with the figures the server sent', async () => {
    const { network } = await openCatalogue()
    await findModels()

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(lastAsked(network, MODELS_ROUTE).toString()).toBe('page=1&pageSize=20')
    expect(within(modelsRegion()).getByText('2 models match.')).toBeVisible()

    const hammer = await rowOf(HAMMER.name)
    expect(within(hammer).getByText(HAMMER.sku)).toBeVisible()
    expect(within(hammer).getByText(HAMMER.categoryName)).toBeVisible()
    expect(within(hammer).getByText('6')).toBeVisible()
    expect(within(hammer).getByText(money(HAMMER.dailyRate))).toBeVisible()
    expect(within(hammer).getByText(`${money(HAMMER.weeklyRate)} a week`)).toBeVisible()
    expect(within(hammer).getByText(money(HAMMER.depositAmount))).toBeVisible()
    expect(within(hammer).getByText(money(HAMMER.lateFeePerDay))).toBeVisible()
    expect(within(hammer).getByText(money(HAMMER.replacementValue))).toBeVisible()
    expect(within(hammer).getByText('Published', { selector: '.pill' })).toBeVisible()
    expect(within(hammer).getByRole('button', { name: `Hide ${HAMMER.name}` })).toBeVisible()

    const breaker = await rowOf(BREAKER.name)
    expect(within(breaker).getByText('Hidden', { selector: '.pill' })).toBeVisible()
    expect(within(breaker).getByText('0')).toBeVisible()
    expect(within(breaker).getByRole('button', { name: `Publish ${BREAKER.name}` })).toBeVisible()
  })

  it('draws a skeleton while it loads', async () => {
    await openCatalogue({ [MODELS_ROUTE]: neverAnswers })

    expect(await screen.findByText('Loading the models.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(modelsRegion().querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read, and reads it again on a retry', async () => {
    const { user, network } = await openCatalogue({ [MODELS_ROUTE]: () => problemResponse(500, { requestId: 'req-models-1' }) })

    const alert = await within(modelsRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the models')
    expect(within(alert).getByText('req-models-1')).toBeVisible()

    network.setRoute(MODELS_ROUTE, () => jsonResponse(modelPage([HAMMER])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await rowOf(HAMMER.name)).toBeVisible()
  })

  it('offers to add the first model when the catalogue has none', async () => {
    const { user } = await openCatalogue({ [MODELS_ROUTE]: () => jsonResponse(modelPage([])) })

    expect(await screen.findByText('The catalogue has no models yet', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(within(modelsRegion()).getByRole('button', { name: 'Add a model' }))

    await waitFor(() => expect(currentAddress()).toBe(`${CATALOGUE}?model=new`))
    expect(await screen.findByRole('heading', { level: 2, name: 'Add a model' }, SCREEN_WAIT)).toHaveFocus()
  })

  it('says so when nothing matches, and clears the filters', async () => {
    const { user, network } = await openCatalogue(
      { [MODELS_ROUTE]: () => jsonResponse(modelPage([])) },
      `${CATALOGUE}?q=chipper&published=false`,
    )

    expect(await screen.findByText('No model matches', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Clear the filters' }))

    await waitFor(() => expect(currentAddress()).toBe(CATALOGUE))
    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).toString()).toBe('page=1&pageSize=20'))
  })
})

describe('the search, the filters and the pages', () => {
  it('searches a moment after the last key and keeps the search in the address', async () => {
    const { user, network } = await openCatalogue()
    await findModels()

    await user.type(screen.getByLabelText('Search by name or stock code'), 'hammer')

    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).get('q')).toBe('hammer'), SCREEN_WAIT)
    expect(currentAddress()).toBe(`${CATALOGUE}?q=hammer`)
    expect(network.requestsTo(MODELS_ROUTE).filter((request) => request.query.has('q'))).toHaveLength(1)
  })

  it('narrows to one category as it is chosen, naming the parent and a category switched off', async () => {
    const { user, network } = await openCatalogue()
    await findModels()
    const menu = screen.getByLabelText('Category')

    expect(within(menu).getByRole('option', { name: 'Rotary Hammers, under Breaking and Drilling' })).toBeInTheDocument()
    expect(within(menu).getByRole('option', { name: 'Welding (switched off)' })).toBeInTheDocument()
    await user.selectOptions(menu, HAMMERS.id)

    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).get('categoryId')).toBe(HAMMERS.id))
    expect(currentAddress()).toBe(`${CATALOGUE}?categoryId=${HAMMERS.id}`)
  })

  it('asks for the hidden models only, and opens on the published ones from the address', async () => {
    const { user, network } = await openCatalogue({}, `${CATALOGUE}?published=true`)
    await findModels()

    expect(lastAsked(network, MODELS_ROUTE).toString()).toBe('published=true&page=1&pageSize=20')
    expect(screen.getByLabelText('Shown to customers')).toHaveValue('true')
    await user.selectOptions(screen.getByLabelText('Shown to customers'), 'false')

    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).get('published')).toBe('false'))
    expect(currentAddress()).toBe(`${CATALOGUE}?published=false`)
  })

  it('asks for another page, keeps it in the address and moves focus to the top of the models', async () => {
    const { user, network } = await openCatalogue({ [MODELS_ROUTE]: () => jsonResponse(modelPage([HAMMER], { total: 41 })) })
    await findModels()

    await user.click(screen.getByRole('button', { name: 'Page 3' }))

    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).get('page')).toBe('3'))
    expect(currentAddress()).toBe(`${CATALOGUE}?page=3`)
    expect(modelsRegion()).toHaveFocus()
  })

  it('puts a refusal under the control it names and lists any other', async () => {
    await openCatalogue(
      {
        [MODELS_ROUTE]: () =>
          problemResponse(422, {
            errors: { fields: { 'query.q': 'Type at least two characters.', 'query.pageSize': 'Ask for 100 at most.' } },
          }),
      },
      `${CATALOGUE}?q=h`,
    )

    expect(await screen.findByText('The list cannot be read with those filters', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText('Search by name or stock code')).toHaveAccessibleDescription('Type at least two characters.')
    expect(screen.getByText('Ask for 100 at most.')).toBeVisible()
  })

  it('offers every category and a way to read them again when the categories fail', async () => {
    const { user, network } = await openCatalogue({ [CATEGORIES_ROUTE]: () => problemResponse(500) })
    await findModels()

    expect(await screen.findByText('The categories could not be read, so only every category is offered.', {}, SCREEN_WAIT)).toBeVisible()
    expect(within(screen.getByLabelText('Category')).getAllByRole('option')).toHaveLength(1)

    const reads = network.requestsTo(CATEGORIES_ROUTE).length
    await user.click(screen.getByRole('button', { name: 'Read the categories again' }))
    await waitFor(() => expect(network.requestsTo(CATEGORIES_ROUTE).length).toBeGreaterThan(reads))
  })
})
