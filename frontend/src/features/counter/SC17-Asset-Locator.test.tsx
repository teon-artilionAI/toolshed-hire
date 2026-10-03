/**
 * Tests for SC-17 Asset Locator, with the network replaced at `fetch`.
 *
 * The list is the server's. Each test says how the locator route answers,
 * types into the search box the way an assistant on the phone would, and reads
 * the page. Too short to search, waiting, failed, nothing found and found,
 * the words for each state, then the paging and the address.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SessionUser } from '../../shared/api/contract'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, mockApi, neverAnswers, problemResponse } from '../../test/api-mock'
import type { ApiMock, RouteHandler, RouteTable } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import { RENTAL_REFERENCE } from '../../test/counter-samples'
import {
  LOCATOR_ROUTE,
  ON_HIRE_UNIT,
  QUARANTINED_UNIT,
  SHELF_UNIT,
  locatorPage,
} from '../../test/overview-samples'
import { SCREEN_WAIT, currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, COUNTER_STAFF, signedInAs } from '../../test/session-samples'

const SEARCH_BOX = 'Asset tag or model'

async function openLocator(
  routes: RouteTable,
  at = '/counter/locator',
  account: SessionUser = COUNTER_STAFF,
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(account), ...routes })
  renderApp(at)
  await findScreenHeading('Where is it')
  return { user: userEvent.setup(), network }
}

function results(): HTMLElement {
  return screen.getByRole('region', { name: 'Units found' })
}

function lastSearch(network: ApiMock): string {
  return network.requestsTo(LOCATOR_ROUTE).at(-1)?.query.toString() ?? ''
}

/** The row of one unit, found by the tag at its head. A unit out of service
 *  names its tag again in its link, so the tag alone is not one element. */
async function rowOf(tag: string): Promise<HTMLElement> {
  const row = (await within(results()).findByRole('rowheader', { name: tag }, SCREEN_WAIT)).closest('tr')
  if (!row) throw new Error(`No row in the results shows ${tag}.`)
  return row
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('before a search', () => {
  it('is connected, asks for two characters, and searches for nothing shorter', async () => {
    const { user, network } = await openLocator({ [LOCATOR_ROUTE]: () => jsonResponse(locatorPage([SHELF_UNIT])) })

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(within(results()).getByRole('status')).toHaveTextContent('Type 2 characters or more to search.')

    await user.type(screen.getByLabelText(SEARCH_BOX), 'T')
    await new Promise((resolve) => setTimeout(resolve, 400))

    expect(network.requestsTo(LOCATOR_ROUTE)).toHaveLength(0)
  })

  it('needs no branch, so an administrator can search straight away', async () => {
    await openLocator({}, '/counter/locator', ADMIN)

    expect(screen.getByLabelText(SEARCH_BOX)).toBeVisible()
    expect(screen.queryByText('Which branch are you working at?')).not.toBeInTheDocument()
  })
})

describe('while the search runs', () => {
  it('says so in a polite status and draws a skeleton', async () => {
    const { user } = await openLocator({ [LOCATOR_ROUTE]: neverAnswers })

    await user.type(screen.getByLabelText(SEARCH_BOX), 'TSH')

    await waitFor(() => expect(within(results()).getByRole('status')).toHaveTextContent('Searching every branch.'))
    expect(results().querySelector('[aria-busy="true"]')).not.toBeNull()
  })
})

describe('when the search fails', () => {
  it('says so with the reference, and searches again on a retry', async () => {
    const { user, network } = await openLocator({
      [LOCATOR_ROUTE]: () => problemResponse(500, { requestId: 'req-locator-1' }),
    })
    await user.type(screen.getByLabelText(SEARCH_BOX), 'TSH')

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the units')
    expect(within(alert).getByText('req-locator-1')).toBeVisible()

    network.setRoute(LOCATOR_ROUTE, () => jsonResponse(locatorPage([SHELF_UNIT])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await rowOf(SHELF_UNIT.assetTag)).toBeVisible()
  })
})

describe('when nothing matches', () => {
  it('says so and suggests what to try', async () => {
    const { user } = await openLocator({ [LOCATOR_ROUTE]: () => jsonResponse(locatorPage([])) })

    await user.type(screen.getByLabelText(SEARCH_BOX), 'zz')

    expect(await screen.findByText('Nothing on the fleet matches that', {}, SCREEN_WAIT)).toBeVisible()
    expect(within(results()).getByRole('status')).toHaveTextContent('Nothing on the fleet matches "zz".')
  })
})

describe('the units found', () => {
  const threeBranches: RouteHandler = () => jsonResponse(locatorPage([ON_HIRE_UNIT, SHELF_UNIT, QUARANTINED_UNIT]))

  it('asks the server with the search, the first page and its size, and keeps the search in the address', async () => {
    const { user, network } = await openLocator({ [LOCATOR_ROUTE]: threeBranches })

    await user.type(screen.getByLabelText(SEARCH_BOX), ' TSH-PC ')

    await rowOf(ON_HIRE_UNIT.assetTag)
    expect(lastSearch(network)).toBe('q=TSH-PC&page=1&pageSize=20')
    expect(currentAddress()).toBe('/counter/locator?q=TSH-PC')
    expect(within(results()).getByRole('status')).toHaveTextContent('3 units match "TSH-PC", across every branch.')
  })

  it('shows each unit with its model, its branch and its state in words', async () => {
    await openLocator({ [LOCATOR_ROUTE]: threeBranches }, '/counter/locator?q=TSH')

    const out = within(await rowOf(ON_HIRE_UNIT.assetTag))
    expect(out.getByText('Out on hire')).toBeVisible()
    expect(out.getByText('Bellville')).toBeVisible()
    expect(out.getByText('B, good working order')).toBeVisible()
    expect(out.getByText(/13 Mar 2026/)).toBeVisible()
    expect(out.getByText(RENTAL_REFERENCE)).toBeVisible()

    const shelf = within(await rowOf(SHELF_UNIT.assetTag))
    expect(shelf.getByText('On the shelf')).toBeVisible()
    expect(shelf.getByText('Cape Town CBD')).toBeVisible()
    expect(shelf.getByText('Not on hire')).toBeVisible()

    const withdrawn = within(await rowOf(QUARANTINED_UNIT.assetTag))
    expect(withdrawn.getByText('Quarantined until inspected')).toBeVisible()
    expect(withdrawn.getByText('Somerset West')).toBeVisible()
    expect(withdrawn.getByText('GBH 2-26 DRE Rotary Hammer')).toBeVisible()
  })

  it('changes nothing, and links only a unit out of service to its damage reports', async () => {
    await openLocator({ [LOCATOR_ROUTE]: threeBranches }, '/counter/locator?q=TSH')

    const table = await screen.findByRole('table', {}, SCREEN_WAIT)
    expect(within(table).queryAllByRole('button')).toHaveLength(0)
    const links = within(table).getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAccessibleName(`Damage reports ${QUARANTINED_UNIT.assetTag}`)
    expect(links[0]).toHaveAttribute('href', `/counter/damage/${QUARANTINED_UNIT.assetTag}`)
    expect(within(await rowOf(QUARANTINED_UNIT.assetTag)).getByRole('link')).toBe(links[0])
    expect(within(table).getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Asset tag',
      'Model',
      'Branch',
      'State',
      'Condition',
      'Due back',
    ])
  })
})

describe('paging', () => {
  const pages: RouteHandler = (request) => {
    const page = Number(request.query.get('page'))
    return jsonResponse(locatorPage([page === 2 ? QUARANTINED_UNIT : SHELF_UNIT], { page, total: 45 }))
  }

  it('shows the page controls from what the server says, and asks for the next page', async () => {
    const { user, network } = await openLocator({ [LOCATOR_ROUTE]: pages }, '/counter/locator?q=TSH')
    await rowOf(SHELF_UNIT.assetTag)
    const controls = screen.getByRole('navigation', { name: 'Unit result pages' })
    expect(within(controls).getByRole('status')).toHaveTextContent('Page 1 of 3')

    await user.click(within(controls).getByRole('button', { name: 'Next' }))

    expect(await rowOf(QUARANTINED_UNIT.assetTag)).toBeVisible()
    expect(lastSearch(network)).toBe('q=TSH&page=2&pageSize=20')
    expect(currentAddress()).toBe('/counter/locator?q=TSH&page=2')
    expect(results()).toHaveFocus()
  })

  it('keeps the search and the page from the address on a reload', async () => {
    const { network } = await openLocator({ [LOCATOR_ROUTE]: pages }, '/counter/locator?q=TSH&page=2')

    expect(await rowOf(QUARANTINED_UNIT.assetTag)).toBeVisible()
    expect(screen.getByLabelText(SEARCH_BOX)).toHaveValue('TSH')
    expect(lastSearch(network)).toBe('q=TSH&page=2&pageSize=20')
  })
})
