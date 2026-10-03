/**
 * What the SC-13 test files share.
 *
 * The booking screen reads the session for the branch the assistant works at,
 * so it is opened inside the whole application. The customer is in the
 * address, the way SC-12 sends an assistant here. A test sets the routes,
 * opens the screen, and books the way an assistant would.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { PLATE_COMPACTOR } from '../../test/catalogue-samples'
import { CUSTOMER_ID } from '../../test/counter-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

export const HEADING = 'New booking'
export const LINES_STEP = 'Step 1 of 4. Choose the dates and the tools'
export const REVIEW_STEP = 'Step 2 of 4. Check the cost'
export const HELD_STEP = 'Step 3 of 4. Confirm the booking'
export const CONFIRMED_STEP = 'Step 4 of 4. The booking is confirmed'
export const PRICE = 'Work out the cost'
export const HOLD = 'Hold the equipment'
export const CONFIRM = 'Confirm the booking'
export const CHANGE_TOOLS = 'Change the dates or the tools'

/** Open SC-13 for a customer, as the counter assistant at Bellville. */
export async function openBooking(
  routes: RouteTable,
  at = `/counter/booking?customer=${CUSTOMER_ID}`,
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(COUNTER_STAFF), ...routes })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** The heading of a step, once the step is on the page. */
export function stepHeading(name: string): Promise<HTMLElement> {
  return screen.findByRole('heading', { level: 2, name }, SCREEN_WAIT)
}

/** Add the plate compactor from the finder, and raise it to two. */
export async function addTwoCompactors(user: UserEvent): Promise<void> {
  const finder = await screen.findByRole('region', { name: 'Tools free at this branch' }, SCREEN_WAIT)
  await user.click(await within(finder).findByRole('button', { name: `Add ${PLATE_COMPACTOR.name}` }, SCREEN_WAIT))
  await user.click(screen.getByRole('button', { name: `One more ${PLATE_COMPACTOR.name}` }))
}

/** Add two compactors and price the booking, landing on the second step. */
export async function priceTwoCompactors(user: UserEvent): Promise<void> {
  await addTwoCompactors(user)
  await user.click(screen.getByRole('button', { name: PRICE }))
  await stepHeading(REVIEW_STEP)
}

/** The figure shown against one term in a list of figures. */
export function figure(term: string | RegExp): HTMLElement {
  const value = within(screen.getByRole('main')).getByText(term).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`No figure is shown for "${term}".`)
  return value
}
