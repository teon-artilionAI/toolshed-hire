/**
 * What the SC-09 test files share.
 *
 * Opening My Account as the signed in customer, the routes that answer with a
 * profile and with no hires yet, and reading one value out of the lists of
 * details.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { PROFILE_ROUTE } from '../../test/account-samples'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { MY_RENTALS_ROUTE, rentalPage } from '../../test/rental-samples'
import { CUSTOMER, signedInAs } from '../../test/session-samples'
import type { MyProfile, SessionUser } from '../../shared/api/contract'

export const HEADING = 'My account'
export const STATEMENT_ROUTE = 'GET /api/me/statement'

/** A statement with no hires in the period, for a screen test that is not about it. */
export const EMPTY_STATEMENT = {
  customerName: 'Wesley Adonis',
  customerEmail: 'wesley.adonis@example.co.za',
  from: '2026-01-01',
  to: '2026-10-24',
  generatedAt: '2026-10-23T09:00:00+00:00',
  totals: {
    hireCount: 0,
    chargesTotalIncVat: '0.00',
    depositHeld: '0.00',
    depositWithheld: '0.00',
    depositRefunded: '0.00',
    balanceDue: '0.00',
  },
  items: [],
}
export const SAVED_TITLE = 'Your details have been updated'

/**
 * Open My Account as the signed in customer, with these routes answering.
 *
 * @param account The signed in account, the seeded customer unless a test
 *   needs another, such as one whose address email cannot reach.
 */
export async function openAccount(
  routes: RouteTable,
  account: SessionUser = CUSTOMER,
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...signedInAs(account),
    [STATEMENT_ROUTE]: () => jsonResponse(EMPTY_STATEMENT),
    ...routes,
  })
  renderApp('/account')
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Routes in which the profile route answers with this profile, and the
 *  customer has no hires yet unless the routes given say otherwise. */
export function withProfile(profile: MyProfile, routes: RouteTable = {}): RouteTable {
  return {
    [PROFILE_ROUTE]: () => jsonResponse(profile),
    [MY_RENTALS_ROUTE]: () => jsonResponse(rentalPage([], { pageSize: 5 })),
    [STATEMENT_ROUTE]: () => jsonResponse(EMPTY_STATEMENT),
    ...routes,
  }
}

/** The value shown against one term in the lists of details. */
export function detail(term: string): HTMLElement {
  const value = screen.getByText(term, { selector: 'dt' }).nextElementSibling
  if (!(value instanceof HTMLElement)) throw new Error(`Nothing is shown against ${term}.`)
  return value
}

/** Wait for the profile and open the form that corrects it. */
export async function startEditing(user: UserEvent): Promise<void> {
  await user.click(await screen.findByRole('button', { name: 'Edit my details' }))
}
