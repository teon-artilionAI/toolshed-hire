/**
 * What the SC-15 test files share.
 *
 * The return screen is opened inside the whole application as the counter
 * assistant at Bellville, by the key of the hire in the address, with the
 * clock pinned to `TEST_NOW`. The routes are set, the screen is opened, and the
 * tests read the page.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import type { Rental } from '../../shared/api/contract'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { RENTAL_ID } from '../../test/counter-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { rentalRoute } from '../../test/rental-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

export const HEADING = 'Return and condition inspection'
export const ASK = 'Take the ticked units back'
export const ANSWER = 'Yes, take them back'
export const QUESTION = 'Take these units back from Thandi Mokoena?'

/** Open SC-15 for a hire, with these routes answering. */
export async function openReturn(
  routes: RouteTable,
  at: string = RENTAL_ID,
  heading: string = HEADING,
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(COUNTER_STAFF), ...routes })
  renderApp(`/counter/return/${at}`)
  await findScreenHeading(heading)
  return { user: userEvent.setup(), network }
}

/** Routes in which the hire is read as this one. */
export function showing(rental: Rental, routes: RouteTable = {}): RouteTable {
  return { [rentalRoute()]: () => jsonResponse(rental), ...routes }
}

/** Wait for the hire to load, by the list of units still out. */
export function findUnitsStillOut(): Promise<HTMLElement> {
  return screen.findByRole('region', { name: 'The units still out' }, SCREEN_WAIT)
}

/** Tick a unit to come back now, by its tag. */
export async function tick(user: UserEvent, tag: string): Promise<void> {
  await user.click(screen.getByRole('checkbox', { name: new RegExp(`^${tag} is back on the counter`) }))
}
