/**
 * What the SC-04 test files share.
 *
 * The basket screen reads the session, so it is opened inside the whole
 * application, the way a person reaches it. The basket is filled first, the
 * routes are set, and the tests read the page.
 */

import { screen, within } from '@testing-library/react'
import type { SessionUser } from '../../shared/api/contract'
import { addToBasket, noteBookingUnderWay } from '../../shared/basket-store'
import { mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { IN_THE_BASKET } from '../../test/reservation-samples'
import { CUSTOMER, SIGNED_OUT, signedInAs } from '../../test/session-samples'

export const BASKET_HEADING = 'Your hire basket'
export const REVIEW = 'Review and book'
export const HOLD = 'Hold this equipment'
export const CONFIRM = 'Confirm this hire'
export const CHANGE_BASKET = 'Change my basket'
export const BASKET_STEP = 'Check your basket'
export const REVIEW_STEP = 'Step 1 of 3. Review the cost'
export const HOLD_STEP = 'Step 2 of 3. Hold the equipment'
export const CONFIRMED_STEP = 'Step 3 of 3. Your hire is confirmed'

/**
 * Open the basket screen with two plate compactors in the basket.
 *
 * @param routes How the API answers, beside the session routes.
 * @param account Who is signed in, or null for a visitor.
 * @param bookingUnderWay The id of a reservation already made from the basket,
 *   which is how the basket is found after a reload in the middle of a booking.
 */
export async function openBasket(
  routes: RouteTable,
  account: SessionUser | null = CUSTOMER,
  bookingUnderWay?: string,
): Promise<ApiMock> {
  addToBasket(IN_THE_BASKET)
  if (bookingUnderWay !== undefined) noteBookingUnderWay(bookingUnderWay)
  const network = mockApi({ ...(account ? signedInAs(account) : SIGNED_OUT), ...routes })
  renderApp('/basket')
  await findScreenHeading(BASKET_HEADING)
  return network
}

/** The heading of a view, once the view is on the page. */
export function stepHeading(name: string): Promise<HTMLElement> {
  return screen.findByRole('heading', { level: 2, name }, SCREEN_WAIT)
}

/** The figure shown against one term in a list of figures. */
export function figure(term: string | RegExp): HTMLElement {
  const value = within(screen.getByRole('main')).getByText(term).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`No figure is shown for "${term}".`)
  return value
}
