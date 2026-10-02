/**
 * What the SC-09 test files share.
 *
 * Opening My Account as the signed in customer, the route that answers with a
 * profile, and reading one value out of the lists of details.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { PROFILE_ROUTE } from '../../test/account-samples'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { CUSTOMER, signedInAs } from '../../test/session-samples'
import type { MyProfile } from '../../shared/api/contract'

export const HEADING = 'My account'
export const SAVED_TITLE = 'Your details have been updated'

/** Open My Account as the signed in customer, with these routes answering. */
export async function openAccount(routes: RouteTable): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(CUSTOMER), ...routes })
  renderApp('/account')
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Routes in which the profile route answers with this profile. */
export function withProfile(profile: MyProfile, routes: RouteTable = {}): RouteTable {
  return { [PROFILE_ROUTE]: () => jsonResponse(profile), ...routes }
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
