/**
 * Tests for SC-06, the sign in screen.
 *
 * I open the whole application on `/signin`, because half of what this screen
 * does is send the person somewhere else once they are signed in. `fetch` is
 * replaced, so each test says how the API answers the sign in and then reads
 * the page.
 *
 * The two password reset states of this screen are in
 * SC06-Password-Reset.test.tsx.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { jsonResponse, mockApi, problemResponse } from '../../test/api-mock'
import type { RouteTable } from '../../test/api-mock'
import { currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import {
  ADMIN,
  COUNTER_STAFF,
  CUSTOMER,
  LOGIN_ROUTE,
  SIGNED_OUT,
  grantFor,
  invalidCredentials,
  signedInAs,
  tooManyAttempts,
} from '../../test/session-samples'
import { REFUSED_MESSAGE } from './sign-in-failure'

const SIGN_IN_HEADING = 'Sign in to Toolshed Hire'
const PASSWORD = 'a-password-typed-by-a-person'

/** Nobody is signed in at start-up, and the rest is what a test adds. */
function signedOutWith(routes: RouteTable): RouteTable {
  return { ...signedInAs(CUSTOMER), ...SIGNED_OUT, ...routes }
}

async function openSignIn(at = '/signin'): Promise<UserEvent> {
  renderApp(at)
  await findScreenHeading(SIGN_IN_HEADING)
  return userEvent.setup()
}

async function fillIn(user: UserEvent, email: string, password = PASSWORD): Promise<void> {
  await user.type(screen.getByLabelText('Email address'), email)
  await user.type(screen.getByLabelText('Password'), password)
}

function submitButton(): HTMLElement {
  return screen.getByRole('button', { name: /^Sign(ing)? in$/ })
}

describe('signing in', () => {
  it('sends the address and password that were typed, once', async () => {
    const network = mockApi(signedOutWith({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) }))
    const user = await openSignIn()

    await fillIn(user, `  ${CUSTOMER.email} `)
    await user.click(submitButton())

    await waitFor(() => expect(currentAddress()).toBe('/'))
    const calls = network.requestsTo(LOGIN_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({ email: CUSTOMER.email, password: PASSWORD })
  })

  it.each([
    ['a customer', CUSTOMER, '/'],
    ['counter staff', COUNTER_STAFF, '/counter'],
    ['an admin', ADMIN, '/admin'],
  ])('lands %s on the home of their role', async (_who, account, home) => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(account)) }))
    const user = await openSignIn()

    await fillIn(user, account.email)
    await user.click(submitButton())

    await waitFor(() => expect(currentAddress()).toBe(home))
  })

  it('lands the person on the screen they were trying to reach', async () => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) }))
    const user = await openSignIn('/signin?next=%2Faccount')

    await fillIn(user, CUSTOMER.email)
    await user.click(submitButton())

    expect(await findScreenHeading('My account')).toBeVisible()
    expect(currentAddress()).toBe('/account')
  })

  it('lands them on their own home when that screen is not for their role', async () => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(CUSTOMER)) }))
    const user = await openSignIn('/signin?next=%2Fadmin%2Fusers')

    await fillIn(user, CUSTOMER.email)
    await user.click(submitButton())

    await waitFor(() => expect(currentAddress()).toBe('/'))
  })

  it('moves focus to the main region of the screen they land on', async () => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: () => jsonResponse(grantFor(COUNTER_STAFF)) }))
    const user = await openSignIn()

    await fillIn(user, COUNTER_STAFF.email)
    await user.click(submitButton())

    await findScreenHeading('Today at the counter')
    await waitFor(() => expect(screen.getByRole('main')).toHaveFocus())
  })

  it('sends somebody who is already signed in straight on', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/signin')

    expect(await findScreenHeading('Today at the counter')).toBeVisible()
    expect(currentAddress()).toBe('/counter')
  })

  it('checks the form before it asks the API', async () => {
    const network = mockApi(signedOutWith({}))
    const user = await openSignIn()

    await user.click(submitButton())

    expect(screen.getByText('Enter the email address on your account.')).toBeVisible()
    expect(screen.getByText('Enter your password.')).toBeVisible()
    expect(network.requestsTo(LOGIN_ROUTE)).toHaveLength(0)
  })
})

describe('while the request is in flight', () => {
  it('disables the button, so it cannot be pressed twice', async () => {
    let answer: (response: Response) => void = () => {}
    const network = mockApi(
      signedOutWith({
        [LOGIN_ROUTE]: () => new Promise<Response>((resolve) => (answer = resolve)),
      }),
    )
    const user = await openSignIn()
    await fillIn(user, CUSTOMER.email)

    await user.click(submitButton())

    const button = await screen.findByRole('button', { name: 'Signing in' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Signing in, please wait')).toBeInTheDocument()
    // Pressing it again, and pressing Enter in a field, both do nothing.
    await user.click(button)
    await user.type(screen.getByLabelText('Password'), '{Enter}')
    expect(network.requestsTo(LOGIN_ROUTE)).toHaveLength(1)

    answer(invalidCredentials())
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeEnabled()
    expect(network.requestsTo(LOGIN_ROUTE)).toHaveLength(1)
  })
})

describe('a sign in that does not work', () => {
  it.each([
    ['a wrong password', () => invalidCredentials()],
    ['an account that is switched off', () => problemResponse(401, { slug: 'inactive-account', detail: 'Deactivated.' })],
    ['an address nobody has', () => problemResponse(401, { slug: 'invalid-credentials', detail: 'Unknown address.' })],
  ])('shows the same message for %s', async (_reason, answer) => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: answer }))
    const user = await openSignIn()

    await fillIn(user, CUSTOMER.email)
    await user.click(submitButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not sign you in')
    expect(alert).toHaveTextContent(REFUSED_MESSAGE)
    // Nothing the server said about the reason reaches the page.
    expect(alert).not.toHaveTextContent(/Deactivated|Unknown address|refused/i)
    expect(currentAddress()).toBe('/signin')
  })

  it('says how long to wait after too many attempts, from Retry-After', async () => {
    mockApi(signedOutWith({ [LOGIN_ROUTE]: () => tooManyAttempts(90) }))
    const user = await openSignIn()

    await fillIn(user, CUSTOMER.email)
    await user.click(submitButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Wait 2 minutes and try again.')
  })

  it('shows the shared error state when the API cannot be reached, and can try again', async () => {
    const network = mockApi(
      signedOutWith({
        [LOGIN_ROUTE]: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )
    const user = await openSignIn()
    await fillIn(user, CUSTOMER.email)

    await user.click(submitButton())

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not sign you in')
    expect(alert).toHaveTextContent('We could not reach Toolshed Hire')
    expect(alert).not.toHaveTextContent(/fetch|TypeError|\/api\//)

    network.setRoute(LOGIN_ROUTE, () => jsonResponse(grantFor(CUSTOMER)))
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(currentAddress()).toBe('/'))
    expect(network.requestsTo(LOGIN_ROUTE)).toHaveLength(2)
  })
})

describe('what the screen no longer does', () => {
  it('lists no accounts and makes no promise about any password', async () => {
    mockApi(signedOutWith({}))
    await openSignIn()

    expect(screen.queryByText(/prototype/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/any password is accepted/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/@toolshedhire\.co\.za/)).not.toBeInTheDocument()
    expect(screen.queryByText(/@buildright\.co\.za/)).not.toBeInTheDocument()
  })
})
