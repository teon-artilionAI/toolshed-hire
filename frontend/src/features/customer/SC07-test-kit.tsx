/**
 * What the SC-07 test files share.
 *
 * With no status chosen, My Reservations asks the list route two questions.
 * One is the page to draw. The other is how many bookings were started and
 * not finished, asked as a page of one whose total is all that is read.
 * `listRoute` answers the second for a test, so a test says what the page
 * holds and, when it matters, how many unfinished bookings there are.
 */

import { screen } from '@testing-library/react'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteHandler, SeenRequest } from '../../test/api-mock'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { DRAFT, LIST_ROUTE, pageOf } from '../../test/reservation-samples'
import { CUSTOMER, signedInAs } from '../../test/session-samples'

export const HEADING = 'My hires'

/** The query the screen counts the unfinished bookings with. */
export const COUNT_QUERY = 'status=DRAFT&page=1&pageSize=1'

function isTheCount(request: SeenRequest): boolean {
  return request.query.toString() === COUNT_QUERY
}

/**
 * How the list route answers.
 *
 * @param page What it answers when asked for a page to draw.
 * @param unfinished How many bookings it says were not finished.
 */
export function listRoute(page: RouteHandler, unfinished = 0): RouteHandler {
  return (request) =>
    isTheCount(request)
      ? jsonResponse(pageOf(unfinished > 0 ? [DRAFT] : [], { pageSize: 1, total: unfinished }))
      : page(request)
}

/**
 * Open My Reservations as the signed in customer.
 *
 * @param route How the list route answers every question put to it.
 */
export async function openListWith(route: RouteHandler, at = '/reservations'): Promise<ApiMock> {
  const network = mockApi({ ...signedInAs(CUSTOMER), [LIST_ROUTE]: route })
  renderApp(at)
  await findScreenHeading(HEADING)
  return network
}

/** Open My Reservations with a page to draw and a count of unfinished bookings. */
export function openList(page: RouteHandler, at = '/reservations', unfinished = 0): Promise<ApiMock> {
  return openListWith(listRoute(page, unfinished), at)
}

/** The query of the most recent request for a page to draw. */
export function lastPageAsked(network: ApiMock): string {
  const pages = network.requestsTo(LIST_ROUTE).filter((request) => !isTheCount(request))
  return pages[pages.length - 1].query.toString()
}

/** The requests that only counted the unfinished bookings. */
export function countRequests(network: ApiMock): SeenRequest[] {
  return network.requestsTo(LIST_ROUTE).filter(isTheCount)
}

export function list(): HTMLElement {
  return screen.getByRole('region', { name: 'My bookings' })
}
