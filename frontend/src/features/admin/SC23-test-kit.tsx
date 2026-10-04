/**
 * What the SC-23 test files share.
 *
 * The screen is opened inside the whole application as the signed in owner,
 * the way a person reaches it. The staff accounts answer with three accounts
 * and the customer holds with three customers unless the routes say otherwise.
 * The routes are set, the screen is opened, and the tests read the page.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { CUSTOMER_HOLDS_ROUTE, USERS_ROUTE, holdPage, userPage } from '../../test/admin-user-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, signedInAs } from '../../test/session-samples'

export const HEADING = 'Users, roles and account holds'

export const USERS = '/admin/users'

export const HOLDS = '/admin/users?view=customers&status=ON_HOLD'

/** Open SC-23 as the owner, on the address given. */
export async function openUsers(routes: RouteTable = {}, at = USERS): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [USERS_ROUTE]: () => jsonResponse(userPage()),
    [CUSTOMER_HOLDS_ROUTE]: () => jsonResponse(holdPage()),
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

/** The body of the last request to a route. */
export function lastBody(network: ApiMock, route: string): unknown {
  const sent = network.requestsTo(route).at(-1)
  if (sent === undefined) throw new Error(`${route} was never asked.`)
  return sent.body
}

/** Wait for the table of staff accounts. */
export async function findAccounts(): Promise<HTMLElement> {
  return within(await screen.findByRole('region', { name: 'The staff accounts' }, SCREEN_WAIT)).findByRole('table', {}, SCREEN_WAIT)
}

/** The row of one account, found by the name at the head of the row. */
export async function rowOf(name: string): Promise<HTMLElement> {
  const table = await findAccounts()
  const header = await within(table).findByRole('rowheader', { name: new RegExp(`^${name}`) }, SCREEN_WAIT)
  const row = header.closest('tr')
  if (!row) throw new Error(`No row of the staff accounts shows ${name}.`)
  return row
}

/** Open one account from its row and wait for its section. */
export async function openAccount(user: UserEvent, name: string): Promise<HTMLElement> {
  await user.click(within(await rowOf(name)).getByRole('button', { name: `Open the account of ${name}` }))
  const heading = await screen.findByRole('heading', { level: 3, name: new RegExp(`^Account of ${name}`) }, SCREEN_WAIT)
  const section = heading.closest('section')
  if (!section) throw new Error(`The heading of ${name} is in no section.`)
  return section
}

/** Wait for the entry of one customer, by the name at its head. */
export async function findCustomer(name: string): Promise<HTMLElement> {
  return screen.findByRole('article', { name }, SCREEN_WAIT)
}
