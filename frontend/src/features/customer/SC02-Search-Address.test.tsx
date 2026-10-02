/**
 * Tests for how the SC-02 search lives in the address, with the network
 * replaced at `fetch`.
 *
 * Most tests open the screen on an address and check two things. What the
 * screen asked the API, and where the address ended up. A reload or a shared
 * link is the same thing as opening the screen on that address.
 */

import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, mockApi } from '../../test/api-mock'
import {
  AVAILABILITY_PAGE,
  TEST_DEFAULT_RETURN,
  TEST_NOW,
  TEST_TODAY,
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

describe('the address', () => {
  it('gains the default dates when the screen is opened bare', async () => {
    const network = mockApi(WORKING)
    openSearch('/search')

    await waitFor(() => expect(address()).toBe(DATED))
    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    expect(lastSearch(network).get('from')).toBe(TEST_TODAY)
    expect(lastSearch(network).get('to')).toBe(TEST_DEFAULT_RETURN)
  })

  it('restores every filter of a shared link', async () => {
    const network = mockApi(WORKING)
    openSearch(`${DATED}&q=rammer&category=compaction&branch=BLV&sort=dailyRateDesc&page=2`)

    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    const asked = lastSearch(network)
    expect(asked.get('q')).toBe('rammer')
    expect(asked.get('category')).toBe('compaction')
    expect(asked.get('branch')).toBe('BLV')
    expect(asked.get('sort')).toBe('dailyRateDesc')
    expect(asked.get('page')).toBe('2')

    expect(screen.getByLabelText('Search by tool or make')).toHaveValue('rammer')
    await waitFor(() => expect(screen.getByLabelText('Category')).toHaveDisplayValue('Compaction'))
    expect(screen.getByLabelText('Branch')).toHaveDisplayValue('Bellville')
    expect(screen.getByLabelText('Sort by')).toHaveDisplayValue('Daily rate, highest first')
    expect(screen.getByLabelText('Collect on')).toHaveValue(TEST_TODAY)
  })

  it('follows a change of category, and starts again from the first page', async () => {
    const user = userEvent.setup()
    const network = mockApi(WORKING)
    openSearch(`${DATED}&page=3`)

    await screen.findByRole('option', { name: 'Compaction' })
    await user.selectOptions(screen.getByLabelText('Category'), 'Compaction')

    await waitFor(() => expect(lastSearch(network).get('category')).toBe('compaction'))
    expect(lastSearch(network).get('page')).toBe('1')
    expect(address()).toBe(`${DATED}&category=compaction`)
  })

  it('follows a change of sort order and of dates', async () => {
    const user = userEvent.setup()
    const network = mockApi(WORKING)
    openSearch(DATED)

    await user.selectOptions(screen.getByLabelText('Sort by'), 'Daily rate, lowest first')
    fireEvent.change(screen.getByLabelText('Bring back on'), { target: { value: '2026-03-19' } })

    await waitFor(() => expect(lastSearch(network).get('to')).toBe('2026-03-19'))
    expect(lastSearch(network).get('sort')).toBe('dailyRateAsc')
    expect(address()).toBe(`/search?from=${TEST_TODAY}&to=2026-03-19&sort=dailyRateAsc`)
  })

  it('lists a child category under its parent', async () => {
    mockApi(WORKING)
    openSearch(DATED)

    expect(
      await screen.findByRole('option', { name: 'Access and Lifting: Ladders, Trestles and Towers' }),
    ).toBeInTheDocument()
  })
})

describe('the text search', () => {
  it('searches once the customer stops typing', async () => {
    const user = userEvent.setup()
    const network = mockApi(WORKING)
    openSearch(DATED)

    await user.type(screen.getByLabelText('Search by tool or make'), 'rammer')

    await waitFor(() => expect(lastSearch(network).get('q')).toBe('rammer'))
    expect(address()).toBe(`${DATED}&q=rammer`)
    // One request when the screen opened and one for the finished word, not
    // one for each letter.
    expect(network.requestsTo(AVAILABILITY_ROUTE).length).toBeLessThanOrEqual(3)
  })

  it('does not send a single letter, which the API would refuse', async () => {
    const network = mockApi(WORKING)
    openSearch(`${DATED}&q=r`)

    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    expect(lastSearch(network).has('q')).toBe(false)
    expect(screen.getByLabelText('Search by tool or make')).toHaveValue('r')
    expect(screen.getByText(/Type 2 letters or more/)).toBeVisible()
  })
})

describe('with a branch chosen', () => {
  it('asks for that branch and says the list is what is free there', async () => {
    const network = mockApi(WORKING)
    openSearch(`${DATED}&branch=BLV`)

    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'Search results' })).toHaveTextContent(
        '2 models are free at Bellville for 4 days.',
      ),
    )
    expect(lastSearch(network).get('branch')).toBe('BLV')
    expect(screen.getByLabelText('Branch')).toHaveAccessibleDescription(
      'Choose one to list only what is free there.',
    )
  })

  it('carries the branch to the model, and never says the branch cannot supply it', async () => {
    mockApi(WORKING)
    openSearch(`${DATED}&branch=BLV`)

    expect(
      await screen.findByRole('link', { name: /See dates and book, BS 60-4 Trench Rammer/ }),
    ).toHaveAttribute(
      'href',
      `/model/bs-60-4-trench-rammer?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}&branch=BLV`,
    )
    expect(screen.queryByText(/Not free at Bellville/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Collect from/ })).not.toBeInTheDocument()
  })

  it('follows a change of branch', async () => {
    const user = userEvent.setup()
    const network = mockApi(WORKING)
    openSearch(DATED)

    await screen.findByRole('heading', { name: 'CP 100 Plate Compactor' })
    await user.selectOptions(screen.getByLabelText('Branch'), 'Somerset West')

    await waitFor(() => expect(lastSearch(network).get('branch')).toBe('SMW'))
    expect(address()).toBe(`${DATED}&branch=SMW`)
  })
})

describe('with more results than fit on a page', () => {
  const FIRST_OF_THREE = { ...AVAILABILITY_PAGE, total: 60 }

  it('announces the page and says which results are showing', async () => {
    mockApi({ ...WORKING, [AVAILABILITY_ROUTE]: () => jsonResponse(FIRST_OF_THREE) })
    openSearch(DATED)

    const pages = await screen.findByRole('navigation', { name: 'Search result pages' })
    expect(within(pages).getByRole('status')).toHaveTextContent('Page 1 of 3')
    expect(within(pages).getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('region', { name: 'Search results' })).toHaveTextContent('Showing 1 to 2.')
  })

  it('asks for the next page and puts it in the address', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...WORKING,
      [AVAILABILITY_ROUTE]: ({ query }) =>
        jsonResponse({ ...FIRST_OF_THREE, page: Number(query.get('page')) }),
    })
    openSearch(DATED)

    await user.click(await screen.findByRole('button', { name: 'Next' }))

    await waitFor(() => expect(lastSearch(network).get('page')).toBe('2'))
    expect(address()).toBe(`${DATED}&page=2`)
    const pages = await screen.findByRole('navigation', { name: 'Search result pages' })
    expect(within(pages).getByRole('status')).toHaveTextContent('Page 2 of 3')
    expect(screen.getByRole('region', { name: 'Search results' })).toHaveFocus()
  })
})
