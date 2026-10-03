/**
 * What the SC-12 test files share.
 *
 * The lookup reads the session for the branch the assistant works at, so it is
 * opened inside the whole application, the way a person reaches it. The routes
 * are set, the screen is opened, and the tests read the page.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import type { SessionUser } from '../../shared/api/contract'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { THANDI, customerRoute } from '../../test/counter-samples'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { LIST_ROUTE, pageOf } from '../../test/reservation-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

export const HEADING = 'Find a customer'
export const SEARCH_BOX = 'Search customers'
export const ADD_CUSTOMER = 'Add this customer'

/** The customer and their bookings, which the panel reads once a customer is chosen. */
export const CHOSEN_READS: RouteTable = {
  [customerRoute()]: () => jsonResponse(THANDI),
  [LIST_ROUTE]: () => jsonResponse(pageOf([])),
}

/**
 * Open SC-12 as a member of staff.
 *
 * @param routes How the API answers, beside the session routes.
 * @param at The address to open, which can carry a search and a customer.
 */
export async function openLookup(
  routes: RouteTable,
  account: SessionUser = COUNTER_STAFF,
  at = '/counter/customers',
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(account), ...routes })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Fill in every answer of the walk in form properly. */
export async function fillInWalkIn(user: UserEvent): Promise<void> {
  await user.type(screen.getByLabelText('Full name'), 'Thandi Mokoena')
  await user.type(screen.getByLabelText('Mobile number'), '082 441 7719')
  await user.type(screen.getByLabelText('Last four characters of the document number'), '5083')
  await user.type(screen.getByLabelText('Billing address, first line'), '12 Loop Street')
  await user.type(screen.getByLabelText('Billing suburb'), 'Gardens')
  await user.type(screen.getByLabelText('Postal code'), '8001')
}
