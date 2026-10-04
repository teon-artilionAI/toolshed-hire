/**
 * What the SC-21 test files share.
 *
 * The register is opened inside the whole application as the signed in
 * owner, the way a person reaches it. The register answers with three units
 * unless the routes say otherwise, each unit answers its own read with its
 * history, and the models answer a search and their own reads. The routes are
 * set, the screen is opened, and the tests read the page.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { BREAKER, HAMMER, MODELS_ROUTE, modelPage, modelRoute } from '../../test/admin-catalogue-samples'
import { ASSETS_ROUTE, INTAKE_UNIT, RETIRED_UNIT, SHELF_UNIT, assetPage, assetRoute, detailOf } from '../../test/admin-asset-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, signedInAs } from '../../test/session-samples'

export const HEADING = 'Asset register'

export const REGISTER = '/admin/assets'

/** Open SC-21 as the owner, on the address given. */
export async function openRegister(routes: RouteTable = {}, at = REGISTER): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [ASSETS_ROUTE]: () => jsonResponse(assetPage()),
    [assetRoute(INTAKE_UNIT.assetTag)]: () => jsonResponse(detailOf(INTAKE_UNIT, [])),
    [assetRoute(SHELF_UNIT.assetTag)]: () => jsonResponse(detailOf(SHELF_UNIT)),
    [assetRoute(RETIRED_UNIT.assetTag)]: () => jsonResponse(detailOf(RETIRED_UNIT, [])),
    [MODELS_ROUTE]: () => jsonResponse(modelPage()),
    [modelRoute(HAMMER.id)]: () => jsonResponse(HAMMER),
    [modelRoute(BREAKER.id)]: () => jsonResponse(BREAKER),
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

/** The region the units are listed in. */
export function unitsRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'The units' })
}

/** Wait for the table of units. */
export async function findUnits(): Promise<HTMLElement> {
  return within(await screen.findByRole('region', { name: 'The units' }, SCREEN_WAIT)).findByRole('table', {}, SCREEN_WAIT)
}

/** The row of one unit, found by its tag at the head of the row. */
export async function rowOf(tag: string): Promise<HTMLElement> {
  const table = await findUnits()
  const header = await within(table).findByRole('rowheader', { name: new RegExp(`^${tag}`) }, SCREEN_WAIT)
  const row = header.closest('tr')
  if (!row) throw new Error(`No row of the register shows ${tag}.`)
  return row
}

/** Wait for a unit to be open, by the heading of its section. */
export async function findUnit(tag: string): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { level: 2, name: `Unit ${tag}` }, SCREEN_WAIT)
  const section = heading.closest('section')
  if (!section) throw new Error(`The heading of ${tag} is in no section.`)
  return section
}
