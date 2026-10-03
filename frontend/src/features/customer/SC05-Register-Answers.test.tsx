/**
 * Tests for what SC-05 says once the API has answered a registration, with
 * the network replaced at `fetch`.
 *
 * A 202 with and without a deliverable email, a 422, a 429, a request that
 * never reached the API, and a branch list that could not be loaded. What
 * these tests hold the screen to is that it says the same thing whoever the
 * address belongs to, and that it never leaves a person waiting for an email
 * that cannot come.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import {
  DELIVERABLE,
  NOT_DELIVERABLE,
  REGISTER_ROUTE,
  refusedFields,
  throttled,
} from '../../test/account-samples'
import { acceptedResponse, mockApi, problemResponse } from '../../test/api-mock'
import { currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import { BRANCHES_ROUTE, SIGNED_OUT } from '../../test/session-samples'
import { DEMONSTRATION_EMAIL_REASON, WITHOUT_THE_LINK } from './email-delivery-note'
import { CHECK_YOUR_EMAIL_HEADING, REGISTRATION_SENT_MESSAGE } from './SC05-Register'
import { EMAIL, HEADING, SUBMIT, fillInEverything, openRegister } from './SC05-test-kit'

describe('after a 202', () => {
  it('says to check the email, in the same words whoever the address belongs to', async () => {
    const { user } = await openRegister(() => acceptedResponse(DELIVERABLE))
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const heading = await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(new RegExp(REGISTRATION_SENT_MESSAGE.replace('.', '\\.')))).toBeVisible()
    expect(screen.getByText(EMAIL)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/signin')
    // Nothing says an account was created, and nothing says one already exists.
    expect(screen.queryByText(/account (is ready|has been created|was created)|already uses that/i)).not.toBeInTheDocument()
    expect(screen.queryByText(DEMONSTRATION_EMAIL_REASON)).not.toBeInTheDocument()
    // The form and the password in it have gone.
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(currentAddress()).toBe('/register')
  })

  it('says plainly when the email cannot be delivered, and what can still be done', async () => {
    const { user } = await openRegister(() => acceptedResponse(NOT_DELIVERABLE))
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })
    expect(screen.getByText(DEMONSTRATION_EMAIL_REASON)).toBeVisible()
    expect(screen.getByText(WITHOUT_THE_LINK)).toBeVisible()
    expect(screen.getByText(/A counter assistant can confirm a booking for you at a branch/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Go to sign in' })).toHaveAttribute('href', '/signin')
  })
})

describe('a registration the API does not accept', () => {
  it('puts each message of a 422 under the field it names, and keeps the form', async () => {
    const { user, network } = await openRegister(() =>
      refusedFields({
        email: 'Use an address at a domain that accepts mail.',
        idDocumentLast4: 'Give four letters or digits.',
        accountStatus: 'This field is not accepted.',
      }),
    )
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const email = screen.getByLabelText('Email address')
    await waitFor(() => expect(email).toBeInvalid())
    expect(email).toHaveAccessibleDescription(/Use an address at a domain that accepts mail\./)
    expect(screen.getByLabelText('Last four characters of the document number')).toHaveAccessibleDescription(
      /Give four letters or digits\./,
    )
    // A message about a field the form has no input for still reaches the person.
    expect(screen.getByText('This field is not accepted.')).toBeVisible()
    expect(screen.queryByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })).not.toBeInTheDocument()

    // The server's sentence goes when the field it was about is changed.
    await user.type(email, 'x')
    expect(email).not.toHaveAccessibleDescription(/Use an address at a domain that accepts mail\./)

    network.setRoute(REGISTER_ROUTE, () => acceptedResponse(DELIVERABLE))
    await user.click(screen.getByRole('button', { name: SUBMIT }))
    expect(await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })).toBeVisible()
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(2)
  })

  it('says how long to wait after a 429, from Retry-After', async () => {
    const { user } = await openRegister(() => throttled(120))
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Wait 2 minutes and try again.')
    expect(screen.getByRole('button', { name: SUBMIT })).toBeEnabled()
  })

  it('shows the shared error state when the API cannot be reached, and can try again', async () => {
    const { user, network } = await openRegister(() => {
      throw new TypeError('Failed to fetch')
    })
    await fillInEverything(user)

    await user.click(screen.getByRole('button', { name: SUBMIT }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not send your details')
    expect(alert).not.toHaveTextContent(/fetch|TypeError|\/api\//)

    network.setRoute(REGISTER_ROUTE, () => acceptedResponse(DELIVERABLE))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: CHECK_YOUR_EMAIL_HEADING })).toBeVisible()
  })
})

describe('when the branches cannot be loaded', () => {
  it('says so in place of the menu, and holds the form back', async () => {
    const network = mockApi({
      ...SIGNED_OUT,
      [BRANCHES_ROUTE]: () => problemResponse(500),
      [REGISTER_ROUTE]: () => acceptedResponse(DELIVERABLE),
    })
    renderApp('/register')
    await findScreenHeading(HEADING)
    const user = userEvent.setup()

    expect(await screen.findByText('We could not load the branches to choose from')).toBeVisible()
    await user.click(screen.getByRole('button', { name: SUBMIT }))

    expect(await screen.findByRole('link', { name: 'Choose the branch you will usually collect from.' })).toHaveAttribute(
      'href',
      '#homeBranchCode',
    )
    expect(network.requestsTo(REGISTER_ROUTE)).toHaveLength(0)
  })
})
