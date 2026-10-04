/**
 * Tests for SC-01 Catalogue Home, with the network replaced at `fetch`.
 *
 * Each test sets how the three catalogue routes answer, renders the screen and
 * then looks at it the way a customer would. The clock is pinned, so the dates
 * the form opens with are the same on every run.
 */

import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { RouteTable } from '../../test/api-mock'
import {
  BRANCHES,
  CATEGORIES,
  MODEL_PAGE,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TODAY,
} from '../../test/catalogue-samples'
import { ADDRESS_TEST_ID } from '../../test/current-address'
import { renderScreen } from '../../test/render-screen'
import CatalogueHome from './SC01-Catalogue-Home'

const BRANCHES_ROUTE = 'GET /api/branches'
const CATEGORIES_ROUTE = 'GET /api/catalogue/categories'
const MODELS_ROUTE = 'GET /api/catalogue/models'

const WORKING: RouteTable = {
  [BRANCHES_ROUTE]: () => jsonResponse(BRANCHES),
  [CATEGORIES_ROUTE]: () => jsonResponse(CATEGORIES),
  [MODELS_ROUTE]: () => jsonResponse(MODEL_PAGE),
}

function openHome() {
  return renderScreen(<CatalogueHome />, { path: '/', at: '/' })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the catalogue is loading', () => {
  it('shows the heading and a working search form straight away', () => {
    mockApi({
      [BRANCHES_ROUTE]: neverAnswers,
      [CATEGORIES_ROUTE]: neverAnswers,
      [MODELS_ROUTE]: neverAnswers,
    })
    openHome()

    expect(
      screen.getByRole('heading', { level: 1, name: 'Hire tools and plant across Cape Town' }),
    ).toBeVisible()
    expect(screen.getByLabelText('Collect on')).toHaveValue(TEST_TODAY)
    expect(screen.getByLabelText('Bring back on')).toHaveValue(TEST_DEFAULT_RETURN)
    expect(screen.getByRole('button', { name: 'See what is free' })).toBeEnabled()
  })

  it('announces what it is waiting for and shows no list yet', () => {
    mockApi({
      [BRANCHES_ROUTE]: neverAnswers,
      [CATEGORIES_ROUTE]: neverAnswers,
      [MODELS_ROUTE]: neverAnswers,
    })
    openHome()

    const announced = screen.getAllByRole('status').map((status) => status.textContent)
    expect(announced).toContain('Loading the categories')
    expect(announced).toContain('Loading tools from the catalogue')
    expect(screen.queryByRole('link', { name: /Compaction/ })).not.toBeInTheDocument()
  })
})

describe('once the catalogue has loaded', () => {
  it('lists each top level category that has something to hire, with its count', async () => {
    mockApi(WORKING)
    openHome()

    const browse = await screen.findByRole('region', { name: 'Browse by job' })
    expect(await within(browse).findByRole('link', { name: /Compaction.*2 models/ })).toBeVisible()
    expect(within(browse).getByRole('link', { name: /Access and Lifting.*1 model$/ })).toBeVisible()
    // A child is already counted inside its parent, so it gets no tile of its own.
    expect(
      within(browse).queryByRole('link', { name: /Ladders, Trestles and Towers/ }),
    ).not.toBeInTheDocument()
    expect(within(browse).getAllByRole('link')).toHaveLength(2)
  })

  it('sends a parent category link to the search for the parent, which brings its children', async () => {
    mockApi(WORKING)
    openHome()

    expect(await screen.findByRole('link', { name: /Access and Lifting/ })).toHaveAttribute(
      'href',
      `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}&category=access-lifting`,
    )
  })

  it('sends a category link to the search for that category and these dates', async () => {
    mockApi(WORKING)
    openHome()

    expect(await screen.findByRole('link', { name: /Compaction.*2 models/ })).toHaveAttribute(
      'href',
      `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}&category=compaction`,
    )
  })

  it('shows the featured models with their price and deposit', async () => {
    const network = mockApi(WORKING)
    openHome()

    const compactor = await screen.findByRole('link', { name: /CP 100 Plate Compactor/ })
    expect(compactor).toHaveTextContent(/R 340[,.]00 per day/)
    expect(compactor).toHaveTextContent(/Deposit R 1.500[,.]00/)
    expect(compactor).toHaveTextContent('Forward plate compactor, 62 kg, 500 mm plate.')
    expect(compactor).toHaveAttribute(
      'href',
      `/model/cp-100-plate-compactor?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`,
    )
    expect(screen.getByRole('link', { name: /BS 60-4 Trench Rammer/ })).toBeVisible()
    expect(network.requestsTo(MODELS_ROUTE)[0].query.get('pageSize')).toBe('6')
  })

  it('shows the size of the catalogue and names the branches', async () => {
    mockApi(WORKING)
    openHome()

    expect(await screen.findByText('Models in the catalogue')).toBeVisible()
    expect(screen.getByText('120')).toBeVisible()
    expect(screen.getByText('Across 2 categories')).toBeVisible()
    expect(screen.getByText('Cape Town CBD, Bellville and Somerset West')).toBeVisible()
    expect(screen.queryByText(/Woodstock/)).not.toBeInTheDocument()
  })

  it('offers the branches the API sent, and any branch', async () => {
    mockApi(WORKING)
    openHome()

    const branch = screen.getByLabelText('Collect from')
    expect(await within(branch).findByRole('option', { name: 'Bellville' })).toBeInTheDocument()
    expect(within(branch).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Any branch',
      'Cape Town CBD',
      'Bellville',
      'Somerset West',
    ])
  })

  it('makes no claim about availability, so it asks no availability question', async () => {
    const network = mockApi(WORKING)
    openHome()

    await screen.findByRole('link', { name: /CP 100 Plate Compactor/ })
    expect(network.requests.map((request) => request.path).sort()).toEqual([
      '/api/branches',
      '/api/catalogue/categories',
      '/api/catalogue/models',
    ])
    expect(screen.queryByText(/\d+ free/i)).not.toBeInTheDocument()
  })
})

describe('the search form', () => {
  it('takes the dates to the search screen', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openHome()

    await user.click(screen.getByRole('button', { name: 'See what is free' }))

    expect(screen.getByTestId(ADDRESS_TEST_ID)).toHaveTextContent(
      `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`,
    )
  })

  it('takes the chosen dates and branch along', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openHome()

    fireEvent.change(screen.getByLabelText('Collect on'), { target: { value: '2026-03-20' } })
    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-23' } })
    await screen.findByRole('option', { name: 'Bellville' })
    await user.selectOptions(screen.getByLabelText('Collect from'), 'Bellville')
    expect(screen.getByText('3 days, 20 Mar 2026 to 23 Mar 2026.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'See what is free' }))

    expect(screen.getByTestId(ADDRESS_TEST_ID)).toHaveTextContent(
      '/search?from=2026-03-20&to=2026-03-23&branch=BLV',
    )
  })

  it('says what is wrong with the dates and stays put', async () => {
    const user = userEvent.setup()
    mockApi(WORKING)
    openHome()

    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-10' } })
    await user.click(screen.getByRole('button', { name: 'See what is free' }))

    expect(screen.getByText(/The return date must be after the collection date/)).toBeVisible()
    expect(screen.getByLabelText('Collect on')).toBeInvalid()
    expect(screen.getByTestId(ADDRESS_TEST_ID)).toHaveTextContent(/^\/$/)
  })

  it('still searches every branch when the branch list could not be loaded', async () => {
    const user = userEvent.setup()
    mockApi({ ...WORKING, [BRANCHES_ROUTE]: () => problemResponse(500) })
    openHome()

    expect(await screen.findByText(/We could not load the branch list/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'See what is free' }))

    expect(screen.getByTestId(ADDRESS_TEST_ID)).toHaveTextContent(
      `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`,
    )
  })
})

describe('when a list fails to load', () => {
  it('says so in plain words with the reference, and keeps the rest of the page', async () => {
    mockApi({
      ...WORKING,
      [CATEGORIES_ROUTE]: () => problemResponse(500, { requestId: 'req-categories-9' }),
    })
    openHome()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load the categories')
    expect(within(alert).getByText('req-categories-9')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')
    expect(await screen.findByRole('link', { name: /CP 100 Plate Compactor/ })).toBeVisible()
  })

  it('loads the list when the customer tries again', async () => {
    const user = userEvent.setup()
    const network = mockApi({ ...WORKING, [MODELS_ROUTE]: () => problemResponse(500) })
    openHome()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load the catalogue')
    network.setRoute(MODELS_ROUTE, () => jsonResponse(MODEL_PAGE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('link', { name: /CP 100 Plate Compactor/ })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when the catalogue is empty', () => {
  it('says there is nothing to browse and nothing to show', async () => {
    mockApi({
      ...WORKING,
      [CATEGORIES_ROUTE]: () => jsonResponse({ items: [] }),
      [MODELS_ROUTE]: () => jsonResponse({ items: [], page: 1, pageSize: 6, total: 0 }),
    })
    openHome()

    expect(await screen.findByText('No categories to browse yet')).toBeVisible()
    expect(await screen.findByText('Nothing in the catalogue yet')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
