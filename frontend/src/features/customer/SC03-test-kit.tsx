/**
 * What the two SC-03 test files share.
 *
 * The routes a working API answers for one model, a way to open the screen on
 * an address, and a reader for what the screen last asked one of the routes.
 */

import { jsonResponse } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import {
  BRANCHES,
  DAILY_QUOTE,
  MODEL_AVAILABILITY,
  PLATE_COMPACTOR_DETAIL,
  TEST_DEFAULT_RETURN,
  TEST_TODAY,
} from '../../test/catalogue-samples'
import { renderScreen } from '../../test/render-screen'
import ModelDetail from './SC03-Product-Model-Detail'

export const SLUG = 'cp-100-plate-compactor'
export const MODEL_ROUTE = `GET /api/catalogue/models/${SLUG}`
export const AVAILABILITY_ROUTE = `GET /api/catalogue/models/${SLUG}/availability`
export const QUOTE_ROUTE = `GET /api/catalogue/models/${SLUG}/quote`
export const BRANCHES_ROUTE = 'GET /api/branches'

/** The model screen on the dates a bare address opens with. */
export const DATED = `/model/${SLUG}?from=${TEST_TODAY}&to=${TEST_DEFAULT_RETURN}`

export const WORKING: RouteTable = {
  [MODEL_ROUTE]: () => jsonResponse(PLATE_COMPACTOR_DETAIL),
  [BRANCHES_ROUTE]: () => jsonResponse(BRANCHES),
  [AVAILABILITY_ROUTE]: () => jsonResponse(MODEL_AVAILABILITY),
  [QUOTE_ROUTE]: () => jsonResponse(DAILY_QUOTE),
}

export function openModel(at: string = DATED) {
  return renderScreen(<ModelDetail />, { path: '/model/:slug', at })
}

/** The query of the most recent request to one route. */
export function lastQuestion(network: ApiMock, route: string): URLSearchParams {
  const requests = network.requestsTo(route)
  if (requests.length === 0) throw new Error(`Nothing has asked ${route} yet.`)
  return requests[requests.length - 1].query
}
