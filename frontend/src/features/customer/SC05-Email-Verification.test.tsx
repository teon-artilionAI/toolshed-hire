/**
 * Tests for where a verification link lands, on SC-05.
 *
 * The link in the email opens `/register#verify=<token>`. I open the whole
 * application on that address, say how the API answers the token, and read
 * the page. What matters most here is what happens to the token. It is posted
 * once, it is taken out of the address, and it is left nowhere.
 */

import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  LINK_TOKEN,
  VERIFY_ROUTE,
  throttled,
  verificationLinkInvalid,
} from '../../test/account-samples'
import { mockApi, neverAnswers, noContentResponse } from '../../test/api-mock'
import type { ApiMock, RouteHandler } from '../../test/api-mock'
import { currentAddress, currentFragment, findScreenHeading, renderApp } from '../../test/render-app'
import { CUSTOMER, SIGNED_OUT, signedInAs } from '../../test/session-samples'
import {
  VERIFICATION_CONFIRMED_HEADING,
  VERIFICATION_INVALID_HEADING,
} from './SC05-Email-Verification'

const HEADING = 'Confirm your email address'
const LINK = `/register#verify=${LINK_TOKEN}`

async function followLink(verify: RouteHandler, signedIn = false): Promise<ApiMock> {
  const network = mockApi({ ...(signedIn ? signedInAs(CUSTOMER) : SIGNED_OUT), [VERIFY_ROUTE]: verify })
  renderApp(LINK)
  await findScreenHeading(HEADING)
  return network
}

describe('a verification link that is good', () => {
  it('posts the token once and says the address is confirmed, with a way to sign in', async () => {
    const network = await followLink(() => noContentResponse())

    const heading = await screen.findByRole('heading', { name: VERIFICATION_CONFIRMED_HEADING })
    await waitFor(() => expect(heading).toHaveFocus())
    // The header offers sign in as well, so I look inside the screen itself.
    expect(within(screen.getByRole('main')).getByRole('link', { name: 'Sign in' })).toHaveAttribute(
      'href',
      '/signin',
    )
    const calls = network.requestsTo(VERIFY_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({ token: LINK_TOKEN })
    // The registration form is not what the link is for.
    expect(screen.queryByLabelText('Full name')).not.toBeInTheDocument()
  })

  it('takes the token out of the address', async () => {
    await followLink(() => noContentResponse())

    await screen.findByRole('heading', { name: VERIFICATION_CONFIRMED_HEADING })
    // The router replaces the address in a transition, so it may land a
    // moment after the answer does.
    await waitFor(() => expect(currentFragment()).toBe(''))
    expect(currentAddress()).toBe('/register')
  })

  it('takes the token out of the address before the API has even answered', async () => {
    await followLink(neverAnswers)

    expect(await screen.findByText('Confirming your email address')).toBeInTheDocument()
    await waitFor(() => expect(currentFragment()).toBe(''))
  })

  it('leaves the token in no storage, no log line and nowhere on the page', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    const logged = [vi.mocked(console.info), vi.mocked(console.warn), vi.mocked(console.error)]

    await followLink(() => noContentResponse())
    await screen.findByRole('heading', { name: VERIFICATION_CONFIRMED_HEADING })
    // The page holds the address the test reads, so it waits for the token to leave it.
    await waitFor(() => expect(currentFragment()).toBe(''))

    expect(JSON.stringify(setItem.mock.calls)).not.toContain(LINK_TOKEN)
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain(LINK_TOKEN)
    for (const level of logged) expect(JSON.stringify(level.mock.calls)).not.toContain(LINK_TOKEN)
    expect(document.body.innerHTML).not.toContain(LINK_TOKEN)
    expect(document.cookie).not.toContain(LINK_TOKEN)
  })

  it('offers the account screen to somebody who is already signed in', async () => {
    await followLink(() => noContentResponse(), true)

    await screen.findByRole('heading', { name: VERIFICATION_CONFIRMED_HEADING })
    expect(screen.getByRole('link', { name: 'Go to my account' })).toHaveAttribute('href', '/account')
  })
})

describe('a verification link that is no longer good', () => {
  it('says so in one way, and sends the person to sign in and ask for a new one', async () => {
    const network = await followLink(verificationLinkInvalid)

    const heading = await screen.findByRole('heading', { name: VERIFICATION_INVALID_HEADING })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(/used already, or it is more than 24 hours old/)).toBeVisible()
    expect(screen.getByText(/sign in and choose Send the link again on your account screen/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Sign in to send a new link' })).toHaveAttribute(
      'href',
      '/signin?next=%2Faccount',
    )
    // Nothing the server said about the link reaches the page.
    expect(screen.queryByText(/not valid/)).not.toBeInTheDocument()
    expect(network.requestsTo(VERIFY_ROUTE)).toHaveLength(1)
    await waitFor(() => expect(currentFragment()).toBe(''))
  })

  it('sends somebody who is signed in straight to their account screen', async () => {
    await followLink(verificationLinkInvalid, true)

    await screen.findByRole('heading', { name: VERIFICATION_INVALID_HEADING })
    expect(screen.getByRole('link', { name: 'Go to my account' })).toHaveAttribute('href', '/account')
  })
})

describe('a verification that could not be made', () => {
  it('says how long to wait after a 429', async () => {
    await followLink(() => throttled(45))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Wait 45 seconds and try again.')
  })

  it('keeps the token for a retry when the API cannot be reached, and confirms on the second try', async () => {
    const user = userEvent.setup()
    const network = await followLink(() => {
      throw new TypeError('Failed to fetch')
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('We could not confirm your email address')
    await waitFor(() => expect(currentFragment()).toBe(''))

    network.setRoute(VERIFY_ROUTE, () => noContentResponse())
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { name: VERIFICATION_CONFIRMED_HEADING })).toBeVisible()
    const calls = network.requestsTo(VERIFY_ROUTE)
    expect(calls).toHaveLength(2)
    expect(calls[1].body).toEqual({ token: LINK_TOKEN })
  })
})

describe('the register screen with no link', () => {
  it('shows the form and posts no token', async () => {
    const network = mockApi(SIGNED_OUT)

    renderApp('/register')

    expect(await findScreenHeading('Create your hire account')).toBeVisible()
    expect(network.requestsTo(VERIFY_ROUTE)).toHaveLength(0)
  })

  it('ignores a fragment that is not a verification link', async () => {
    const network = mockApi(SIGNED_OUT)

    renderApp('/register#email')

    expect(await findScreenHeading('Create your hire account')).toBeVisible()
    expect(currentFragment()).toBe('#email')
    expect(network.requestsTo(VERIFY_ROUTE)).toHaveLength(0)
  })
})
