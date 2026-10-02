/**
 * Tests for choosing a new password on SC-06, with the network replaced at
 * `fetch`.
 *
 * The link in the email opens `/signin#reset=<token>`. I open the whole
 * application on that address, say how the API answers, and read the page.
 * What these tests hold the screen to is a token that is posted once, taken
 * out of the address and left nowhere, and a password rule of twelve
 * characters.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  LINK_TOKEN,
  RESET_COMPLETE_ROUTE,
  refusedFields,
  resetLinkInvalid,
  throttled,
} from '../../test/account-samples'
import { mockApi, noContentResponse } from '../../test/api-mock'
import type { ApiMock, RouteHandler } from '../../test/api-mock'
import { currentAddress, currentFragment, findScreenHeading, renderApp } from '../../test/render-app'
import { CUSTOMER, LOGOUT_ROUTE, SIGNED_OUT, signedInAs } from '../../test/session-samples'
import { RESET_DONE_HEADING, RESET_LINK_INVALID_HEADING } from './password-reset-panels'

const SIGN_IN_HEADING = 'Sign in to Toolshed Hire'
const REQUEST_HEADING = 'Reset your password'
const COMPLETE_HEADING = 'Choose a new password'
const NEW_PASSWORD = 'a-new-password'

async function followLink(route: RouteHandler): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...SIGNED_OUT, [RESET_COMPLETE_ROUTE]: route })
  renderApp(`/signin#reset=${LINK_TOKEN}`)
  await findScreenHeading(COMPLETE_HEADING)
  return { user: userEvent.setup(), network }
}

async function typeNewPassword(user: UserEvent, password = NEW_PASSWORD, again = password): Promise<void> {
  await user.type(screen.getByLabelText('New password'), password)
  await user.type(screen.getByLabelText('Confirm new password'), again)
}

describe('choosing a new password from the link', () => {
  it('takes the token out of the address at once and shows the form', async () => {
    const { network } = await followLink(() => noContentResponse())

    expect(screen.getByLabelText('New password')).toBeVisible()
    expect(screen.getByText('At least 12 characters.')).toBeVisible()
    await waitFor(() => expect(currentFragment()).toBe(''))
    expect(currentAddress()).toBe('/signin')
    expect(network.requestsTo(RESET_COMPLETE_ROUTE)).toHaveLength(0)
  })

  it('posts the token and the password once, and says every device has been signed out', async () => {
    const { user, network } = await followLink(() => noContentResponse())
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    const heading = await screen.findByRole('heading', { name: RESET_DONE_HEADING })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(/Every device that was signed in to your account has been signed out/)).toBeVisible()
    const calls = network.requestsTo(RESET_COMPLETE_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({ token: LINK_TOKEN, newPassword: NEW_PASSWORD })

    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
    expect(screen.getByLabelText('Email address')).toBeVisible()
  })

  it('leaves the token in no storage, no log line and nowhere on the page', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    const logged = [vi.mocked(console.info), vi.mocked(console.warn), vi.mocked(console.error)]
    const { user } = await followLink(() => noContentResponse())
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))
    await screen.findByRole('heading', { name: RESET_DONE_HEADING })
    // The page holds the address the test reads, so it waits for the token to leave it.
    await waitFor(() => expect(currentFragment()).toBe(''))

    expect(JSON.stringify(setItem.mock.calls)).not.toContain(LINK_TOKEN)
    expect(JSON.stringify({ ...window.localStorage, ...window.sessionStorage })).not.toContain(LINK_TOKEN)
    for (const level of logged) {
      const lines = JSON.stringify(level.mock.calls)
      expect(lines).not.toContain(LINK_TOKEN)
      expect(lines).not.toContain(NEW_PASSWORD)
    }
    expect(document.body.innerHTML).not.toContain(LINK_TOKEN)
    expect(currentFragment()).toBe('')
  })

  it.each([
    ['a password under twelve characters', 'eleven-char', 'eleven-char', 'Passwords need at least 12 characters. Yours has 11.'],
    ['two passwords that differ', NEW_PASSWORD, 'a-new-passwerd', 'The two passwords are not the same. Retype them both.'],
    ['no password at all', '', '', 'Choose a password so you can sign in again later.'],
  ])('holds back %s, and says why beside the field', async (_what, password, again, message) => {
    const { user, network } = await followLink(() => noContentResponse())
    if (password) await typeNewPassword(user, password, again)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    expect(screen.getByText(message)).toBeVisible()
    expect(network.requestsTo(RESET_COMPLETE_ROUTE)).toHaveLength(0)
    expect(screen.queryByRole('heading', { name: RESET_DONE_HEADING })).not.toBeInTheDocument()
  })

  it('puts a 422 about the password under the field, and can be sent again', async () => {
    const { user, network } = await followLink(() =>
      refusedFields({ newPassword: 'Choose a password that is harder to guess.' }),
    )
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    const field = screen.getByLabelText('New password')
    await waitFor(() => expect(field).toHaveAccessibleDescription(/Choose a password that is harder to guess\./))
    expect(field).toBeInvalid()

    network.setRoute(RESET_COMPLETE_ROUTE, () => noContentResponse())
    await user.click(screen.getByRole('button', { name: 'Change my password' }))
    expect(await screen.findByRole('heading', { name: RESET_DONE_HEADING })).toBeVisible()
    expect(network.requestsTo(RESET_COMPLETE_ROUTE)).toHaveLength(2)
  })

  it('says a dead link is dead in one way, and offers to ask for a new one', async () => {
    const { user, network } = await followLink(resetLinkInvalid)
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    const heading = await screen.findByRole('heading', { name: RESET_LINK_INVALID_HEADING })
    await waitFor(() => expect(heading).toHaveFocus())
    expect(screen.getByText(/used already, or it is more than 60 minutes old/)).toBeVisible()
    expect(screen.queryByText(/not valid/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ask for a new link' }))

    expect(await findScreenHeading(REQUEST_HEADING)).toBeVisible()
    expect(screen.getByLabelText('Email address')).toBeVisible()
    expect(network.requestsTo(RESET_COMPLETE_ROUTE)).toHaveLength(1)
  })

  it('says how long to wait after a 429, and keeps the form', async () => {
    const { user } = await followLink(() => throttled(30))
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Wait 30 seconds and try again.')
    expect(screen.getByRole('button', { name: 'Change my password' })).toBeEnabled()
  })

  it('is followed by somebody who is signed in, and signs this page out with the rest', async () => {
    const network = mockApi({ ...signedInAs(CUSTOMER), [RESET_COMPLETE_ROUTE]: () => noContentResponse() })
    renderApp(`/signin#reset=${LINK_TOKEN}`)
    await findScreenHeading(COMPLETE_HEADING)
    const user = userEvent.setup()
    await typeNewPassword(user)

    await user.click(screen.getByRole('button', { name: 'Change my password' }))

    expect(await screen.findByRole('heading', { name: RESET_DONE_HEADING })).toBeVisible()
    expect(network.requestsTo(LOGOUT_ROUTE)).toHaveLength(1)
    expect(currentAddress()).toBe('/signin')
    // The header offers sign in again, which it only does to somebody signed out.
    expect(await screen.findByRole('link', { name: 'Sign in' })).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
  })
})
