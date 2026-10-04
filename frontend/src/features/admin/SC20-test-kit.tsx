/**
 * What the SC-20 test files share.
 *
 * The catalogue is opened inside the whole application as the signed in
 * owner, the way a person reaches it. The categories answer with three and the
 * models with two unless the routes say otherwise, and each model answers its
 * own read. The routes are set, the screen is opened, and the tests read the
 * page.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import {
  BREAKER,
  CATEGORIES_ROUTE,
  HAMMER,
  MODELS_ROUTE,
  categoryList,
  modelPage,
  modelRoute,
} from '../../test/admin-catalogue-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, signedInAs } from '../../test/session-samples'

export const HEADING = 'Catalogue and pricing'

/** Open SC-20 as the owner, on the address given. */
export async function openCatalogue(
  routes: RouteTable = {},
  at = '/admin/catalogue',
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(ADMIN),
    [CATEGORIES_ROUTE]: () => jsonResponse(categoryList()),
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

/** The region the models are listed in. */
export function modelsRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'The models' })
}

/** Wait for the table of models. */
export async function findModels(): Promise<HTMLElement> {
  return within(await screen.findByRole('region', { name: 'The models' }, SCREEN_WAIT)).findByRole(
    'table',
    {},
    SCREEN_WAIT,
  )
}

/** A name as the start of a pattern, with every character taken literally. */
function startsWith(name: string): RegExp {
  return new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
}

/** The row of one model, found by its name at the head of the row. */
export async function rowOf(name: string): Promise<HTMLElement> {
  const table = await findModels()
  const header = await within(table).findByRole('rowheader', { name: startsWith(name) }, SCREEN_WAIT)
  const row = header.closest('tr')
  if (!row) throw new Error(`No row of the models shows ${name}.`)
  return row
}

/** The region the categories are listed in. */
export function categoriesRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Categories' })
}

/** Wait for the table of categories. */
export async function findCategories(): Promise<HTMLElement> {
  return within(await screen.findByRole('region', { name: 'Categories' }, SCREEN_WAIT)).findByRole(
    'table',
    {},
    SCREEN_WAIT,
  )
}

/** The row of one category, found by its name at the head of the row. */
export async function categoryRowOf(name: string): Promise<HTMLElement> {
  const table = await findCategories()
  const header = await within(table).findByRole('rowheader', { name: startsWith(name) }, SCREEN_WAIT)
  const row = header.closest('tr')
  if (!row) throw new Error(`No row of the categories shows ${name}.`)
  return row
}
