/**
 * Tests for SC-02 Availability Search Results, with the network replaced at
 * `fetch`.
 *
 * This file covers the states of the screen. Loading, loaded, empty, failed
 * and refused. How the search follows the address is in
 * SC02-Search-Address.test.tsx. The clock is pinned, so the dates are the same
 * on every run.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import {
  AVAILABILITY_PAGE,
  EMPTY_AVAILABILITY_PAGE,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TODAY,
  TRENCH_RAMMER,
} from '../../test/catalogue-samples'
import {
  AVAILABILITY_ROUTE,
  DATED,
  WORKING,
  address,
  lastSearch,
  openSearch,
} from './SC02-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('while the search is running', () => {
  it('says it is checking and shows no results yet', () => {
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: neverAnswers })
    openSearch(DATED)

    expect(screen.getByRole('heading', { level: 1, name: 'What is free for your dates' })).toBeVisible()
    const results = screen.getByRole('region', { name: 'Search results' })
    expect(within(results).getByRole('status')).toHaveTextContent(
      'Checking what is free for your dates.',
    )
    expect(within(results).queryByRole('heading')).not.toBeInTheDocument()
  })
})

describe('once the search has answered', () => {
  it('asks the API for the dates in the address', async () => {
    const network = mockApi(WORKING)
    openSearch('/search?from=2026-03-20&to=2026-03-23')

    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    const asked = lastSearch(network)
    expect(asked.get('from')).toBe('2026-03-20')
    expect(asked.get('to')).toBe('2026-03-23')
    expect(asked.get('sort')).toBe('name')
    expect(asked.get('page')).toBe('1')
    expect(asked.get('pageSize')).toBe('24')
    expect(asked.has('q')).toBe(false)
    expect(asked.has('branch')).toBe(false)
  })

  it('announces how many models matched and for how long', async () => {
    mockApi(WORKING)
    openSearch(DATED)

    const results = screen.getByRole('region', { name: 'Search results' })
    await waitFor(() =>
      expect(within(results).getByRole('status')).toHaveTextContent(
        '2 models match, across every branch, for 4 days.',
      ),
    )
  })

  it('shows each model with its price and a link to its detail', async () => {
    mockApi(WORKING)
    openSearch(DATED)

    expect(await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })).toBeVisible()
    expect(screen.getByText(/R 340[,.]00/)).toBeVisible()
    expect(screen.getByRole('link', { name: /See dates and book, CP 100 Plate Compactor/ })).toHaveAttribute(
      'href',
      `/model/cp-100-plate-compactor?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`,
    )
  })

  it('says free or not free for every branch, and never a count', async () => {
    mockApi(WORKING)
    openSearch(DATED)

    const compactor = await screen.findByRole('list', { name: 'CP 100 Plate Compactor at each branch' })
    expect(within(compactor).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Cape Town CBD: Free',
      'Bellville: Free',
      'Somerset West: Not free',
    ])
    const rammer = screen.getByRole('list', { name: 'BS 60-4 Trench Rammer at each branch' })
    expect(within(rammer).getByText('Cape Town CBD: Not free')).toBeVisible()
    const results = screen.getByRole('region', { name: 'Search results' })
    expect(results).not.toHaveTextContent(/\d+ (free|units?|left|in stock)/i)
  })
})

describe('when the dates are outside what one model hires for', () => {
  const WEEKEND_ONLY = { ...TRENCH_RAMMER, minHireDays: 1, maxHireDays: 3 }

  it('says so on that row, because the search itself does not check it', async () => {
    mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () =>
        jsonResponse({
          ...AVAILABILITY_PAGE,
          items: [AVAILABILITY_PAGE.items[0], { ...AVAILABILITY_PAGE.items[1], model: WEEKEND_ONLY }],
        }),
    })
    openSearch(DATED)

    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    const rows = within(screen.getByRole('region', { name: 'Search results' }))
      .getAllByRole('listitem')
      .filter((item) => within(item).queryByRole('heading', { level: 3 }) !== null)
    expect(rows).toHaveLength(2)
    expect(rows[1]).toHaveTextContent(
      'This tool hires for 1 to 3 days and your dates are 4. Open it to choose a period it allows.',
    )
    expect(rows[0]).not.toHaveTextContent('This tool hires for')
  })
})

describe('when nothing matches', () => {
  it('says so in words that fit a search of every branch', async () => {
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: () => jsonResponse(EMPTY_AVAILABILITY_PAGE) })
    openSearch(`${DATED}&q=unobtainium`)

    expect(await screen.findByText('Nothing matches that search')).toBeVisible()
  })

  it('says so and clears the filters on request', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () => jsonResponse(EMPTY_AVAILABILITY_PAGE),
    })
    openSearch(`${DATED}&q=unobtainium&category=compaction&branch=BLV`)

    expect(await screen.findByText('Nothing in that search is free at Bellville')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear the filters' }))

    await waitFor(() => expect(address()).toBe(DATED))
    expect(screen.getByLabelText('Search by tool or make')).toHaveValue('')
    expect(lastSearch(network).has('category')).toBe(false)
  })
})

describe('when the search fails', () => {
  it('says so in plain words with the reference, and searches again on request', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () => problemResponse(500, { requestId: 'req-search-7' }),
    })
    openSearch(DATED)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not load what is free for your dates')
    expect(within(alert).getByText('req-search-7')).toBeVisible()
    expect(alert).not.toHaveTextContent('500')
    expect(screen.getByRole('region', { name: 'Search results' })).toHaveTextContent(
      'The search did not finish.',
    )

    network.setRoute(AVAILABILITY_ROUTE, () => jsonResponse(AVAILABILITY_PAGE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('when the API refuses the dates in the address', () => {
  const REFUSAL = () =>
    problemResponse(422, {
      errors: {
        from: 'Collection cannot be in the past.',
        to: 'The return date must be after the collection date.',
        pageSize: 'Must be 50 or fewer.',
      },
    })

  it('shows each message under the field it is about', async () => {
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: REFUSAL })
    openSearch('/search?from=2026-03-01&to=2026-02-20')

    expect(await screen.findByText('Collection cannot be in the past.')).toBeVisible()
    expect(screen.getByText('The return date must be after the collection date.')).toBeVisible()
    expect(screen.getByLabelText('Collect on')).toBeInvalid()
    expect(screen.getByLabelText('Collect on')).toHaveAccessibleDescription(
      'Collection cannot be in the past.',
    )
    expect(screen.getByLabelText('Bring back on')).toBeInvalid()
  })

  it('lists a refusal that belongs to no field, and offers no pointless retry', async () => {
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: REFUSAL })
    openSearch('/search?from=2026-03-01&to=2026-02-20')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We cannot search with those details')
    expect(within(alert).getByText('Must be 50 or fewer.')).toBeVisible()
    expect(within(alert).queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('puts a refused category and branch, named the way the API names them, under their own fields', async () => {
    mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () =>
        problemResponse(422, {
          errors: {
            fields: {
              'query.category': 'That is not a category of this catalogue.',
              'query.branch': 'That is not a trading branch.',
            },
          },
        }),
    })
    openSearch(`${DATED}&category=nope&branch=XXX`)

    expect(await screen.findByText('That is not a category of this catalogue.')).toBeVisible()
    expect(screen.getByLabelText('Category')).toBeInvalid()
    expect(screen.getByLabelText('Category')).toHaveAccessibleDescription(
      'That is not a category of this catalogue.',
    )
    expect(screen.getByLabelText('Branch')).toBeInvalid()
    expect(screen.getByLabelText('Branch')).toHaveAccessibleDescription(
      'Choose one to list only what is free there. That is not a trading branch.',
    )
    expect(within(screen.getByRole('alert')).queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('does not crash on a date that is not a date', async () => {
    const network = mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: () =>
        problemResponse(422, { errors: { fields: { 'query.from': 'Input should be a valid date.' } } }),
    })
    openSearch('/search?from=banana&to=2026-03-16')

    expect(await screen.findByText('Input should be a valid date.')).toBeVisible()
    expect(screen.getByRole('heading', { level: 1, name: 'What is free for your dates' })).toBeVisible()
    expect(lastSearch(network).get('from')).toBe('banana')
    // Asked once. A refusal is never retried.
    expect(network.requestsTo(AVAILABILITY_ROUTE)).toHaveLength(1)
  })

  it('asks for a date when one is missing, and does not ask the API', async () => {
    const network = mockApi(WORKING)
    openSearch('/search?from=&to=2026-03-16')

    expect(await screen.findByText('Choose a collection date.')).toBeVisible()
    expect(screen.getByRole('region', { name: 'Search results' })).toHaveTextContent(
      'Waiting on a usable pair of dates.',
    )
    expect(network.requestsTo(AVAILABILITY_ROUTE)).toHaveLength(0)
  })
})
