/**
 * What the SC-22 test files share.
 *
 * The report is opened inside the whole application as the signed in owner,
 * the way a person reaches it, with the branch and category lists answered.
 * The routes are set, the screen is opened, and the tests read the page.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { CATEGORIES } from '../../test/catalogue-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { CATEGORIES_ROUTE, REPORT, REPORT_ROUTE } from '../../test/report-samples'
import { ADMIN, signedInAs } from '../../test/session-samples'

export const HEADING = 'Utilisation and gross contribution'

/** Open SC-22 as the owner, on the address given. The report answers with
 *  `REPORT` unless the routes say otherwise. */
export async function openReport(
  routes: RouteTable = {},
  at = '/admin/reports',
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [CATEGORIES_ROUTE]: () => jsonResponse(CATEGORIES),
    [REPORT_ROUTE]: () => jsonResponse(REPORT),
    ...routes,
  })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Wait for a loaded report, which has the table of rows. */
export function findRows(): Promise<HTMLElement> {
  return screen.findByRole('table', {}, SCREEN_WAIT)
}

/** The query of the last report request. */
export function lastAsked(network: ApiMock): URLSearchParams {
  const asked = network.requestsTo(REPORT_ROUTE).at(-1)?.query
  if (asked === undefined) throw new Error('The report was never asked for.')
  return asked
}

/** The names of the rows in the table, in the order they are drawn. */
export function rowNames(): string[] {
  const table = screen.getByRole('table')
  return within(table)
    .getAllByRole('rowheader')
    .map((cell) => cell.firstElementChild?.textContent ?? '')
}
