/**
 * What the two SC-02 test files share.
 *
 * The routes a working API answers, a way to open the screen on an address,
 * and two readers. One for what the screen last asked the API, and one for the
 * address the screen is on.
 */

import { screen } from '@testing-library/react'
import { jsonResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import {
  AVAILABILITY_PAGE,
  BRANCHES,
  CATEGORIES,
  TEST_DEFAULT_RETURN,
  TEST_TODAY,
} from '../../test/catalogue-samples'
import { ADDRESS_TEST_ID } from '../../test/current-address'
import { renderScreen } from '../../test/render-screen'
import SearchResults from './SC02-Availability-Search-Results'

export const AVAILABILITY_ROUTE = 'GET /api/catalogue/availability'

/** The search screen on the dates a bare `/search` opens with. */
export const DATED = `/search?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`

export const WORKING: RouteTable = {
  'GET /api/branches': () => jsonResponse(BRANCHES),
  'GET /api/catalogue/categories': () => jsonResponse(CATEGORIES),
  [AVAILABILITY_ROUTE]: () => jsonResponse(AVAILABILITY_PAGE),
}

export function openSearch(at: string) {
  return renderScreen(<SearchResults />, { path: '/search', at })
}

/** The query of the most recent availability request. */
export function lastSearch(network: ApiMock): URLSearchParams {
  const requests = network.requestsTo(AVAILABILITY_ROUTE)
  return requests[requests.length - 1].query
}

/** The address the screen is on, path and query string. */
export function address(): string {
  return screen.getByTestId(ADDRESS_TEST_ID).textContent ?? ''
}
