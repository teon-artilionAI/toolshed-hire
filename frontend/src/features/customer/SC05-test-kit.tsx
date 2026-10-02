/**
 * What the SC-05 test files share.
 *
 * Opening the registration form with the branches answering, and filling in
 * every answer the way a person would.
 */

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { REGISTER_ROUTE } from '../../test/account-samples'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteHandler } from '../../test/api-mock'
import { BRANCHES } from '../../test/catalogue-samples'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { BRANCHES_ROUTE, SIGNED_OUT } from '../../test/session-samples'

export const HEADING = 'Create your hire account'
export const EMAIL = 'thandi@example.co.za'
export const PASSWORD = 'a-long-password'
export const SUBMIT = 'Create my account'

/** Open the form as a visitor. @param register How the register route answers. */
export async function openRegister(register: RouteHandler): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({
    ...SIGNED_OUT,
    [BRANCHES_ROUTE]: () => jsonResponse(BRANCHES),
    [REGISTER_ROUTE]: register,
  })
  renderApp('/register')
  await findScreenHeading(HEADING)
  // The branches arrive, and the first one stands in until another is chosen.
  await screen.findByRole('option', { name: 'Cape Town CBD, Woodstock' })
  return { user: userEvent.setup(), network }
}

/** Fill in every answer properly, choosing the Bellville branch. */
export async function fillInEverything(user: UserEvent): Promise<void> {
  await user.type(screen.getByLabelText('Full name'), 'Thandi Mokoena')
  await user.type(screen.getByLabelText('Email address'), EMAIL)
  await user.type(screen.getByLabelText('Mobile number'), '082 441 7719')
  await user.type(screen.getByLabelText('Last four characters of the document number'), '5083')
  await user.type(screen.getByLabelText('Billing address, first line'), '12 Loop Street')
  await user.type(screen.getByLabelText('Billing suburb'), 'Gardens')
  await user.type(screen.getByLabelText('Postal code'), '8001')
  await user.selectOptions(screen.getByLabelText('Usual collection branch'), 'Bellville, Stikland')
  await user.type(screen.getByLabelText('Password'), PASSWORD)
  await user.type(screen.getByLabelText('Confirm password'), PASSWORD)
  await user.click(screen.getByRole('checkbox'))
}
