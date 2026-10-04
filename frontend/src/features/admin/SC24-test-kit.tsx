/**
 * What the SC-24 test files share.
 *
 * The log is opened inside the whole application as the signed in owner, the
 * way a person reaches it. The trail answers with two events and the log with
 * two emails unless the routes say otherwise. The routes are set, the screen
 * is opened, and the tests read the page.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import {
  AUDIT_ROUTE,
  CONFIRMED_EVENT,
  FAILED_EMAIL,
  NOTIFICATIONS_ROUTE,
  SENT_EMAIL,
  SWEEP_EVENT,
  auditPage,
  emailPage,
} from '../../test/audit-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, signedInAs } from '../../test/session-samples'

export const HEADING = 'Audit and notification log'

/** Open SC-24 as the owner, on the address given. */
export async function openLog(routes: RouteTable = {}, at = '/admin/audit'): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [AUDIT_ROUTE]: () => jsonResponse(auditPage([CONFIRMED_EVENT, SWEEP_EVENT])),
    [NOTIFICATIONS_ROUTE]: () => jsonResponse(emailPage([FAILED_EMAIL, SENT_EMAIL])),
    ...routes,
  })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** The query of the last request to a route. */
export function lastAsked(network: ApiMock, route: string): URLSearchParams {
  const asked = network.requestsTo(route).at(-1)?.query
  if (asked === undefined) throw new Error(`${route} was never asked.`)
  return asked
}

/** Wait for the loaded list of events. */
export function findEvents(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: 'Events, newest first' }, SCREEN_WAIT)
}

/** Wait for the loaded list of emails. */
export function findEmails(): Promise<HTMLElement> {
  return screen.findByRole('list', { name: 'Emails, newest first' }, SCREEN_WAIT)
}
