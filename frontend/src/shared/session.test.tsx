/**
 * Tests for what the session provider does with the router and the cache.
 *
 * A first visit, signing out, and a session that ends underneath a person.
 * Each needs the whole application around it, because the question is where
 * the person ends up and what is left in memory.
 */

import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { getCurrentUser } from './api/auth'
import { jsonResponse, mockApi, noContentResponse } from '../test/api-mock'
import type { RouteTable } from '../test/api-mock'
import { currentAddress, findScreenHeading, renderApp } from '../test/render-app'
import {
  ACCESS_TOKEN,
  CUSTOMER,
  LOGIN_ROUTE,
  LOGOUT_ROUTE,
  ME_ROUTE,
  REFRESH_ROUTE,
  bearerOf,
  grantFor,
  sessionExpired,
  signedInAs,
  tokenRefused,
} from '../test/session-samples'
import { SESSION_HINT_KEY } from './session-markers'

/** The customer header writes the label twice, once for each screen width,
 *  and a stylesheet hides one of them. A test has no stylesheet, so it sees
 *  both, and the name is matched loosely. */
const SIGN_OUT = /Sign out/

const SIGN_IN_HEADING = 'Sign in to Toolshed Hire'
const CATALOGUE_HEADING = 'Hire tools and plant across Cape Town'
const PRIVATE_KEY = ['reservations', 'mine']

/**
 * A session that start-up finds, and that the server then ends.
 *
 * The first refresh answers with the session. Every later one says it has
 * expired, and the protected endpoint refuses the token it was given.
 */
function sessionThatEnds(): RouteTable {
  let refreshes = 0
  return {
    ...signedInAs(CUSTOMER),
    [REFRESH_ROUTE]: () => {
      refreshes += 1
      return refreshes === 1 ? jsonResponse(grantFor(CUSTOMER)) : sessionExpired()
    },
    [ME_ROUTE]: () => tokenRefused(),
    'GET /api/health': () =>
      jsonResponse({
        status: 'healthy',
        environment: 'test',
        databaseReachable: true,
        btreeGistInstalled: true,
        revision: 'test',
      }),
  }
}

describe('a first visit', () => {
  it('shows the screen without asking the server whether there is a session', async () => {
    window.localStorage.removeItem(SESSION_HINT_KEY)
    const network = mockApi(signedInAs(CUSTOMER))

    renderApp('/signin')

    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(0)
  })
})

describe('signing out', () => {
  it('tells the server, drops the token and the cache, and goes to the catalogue', async () => {
    const user = userEvent.setup()
    const network = mockApi({ ...signedInAs(CUSTOMER), [ME_ROUTE]: () => tokenRefused() })
    const { queryClient } = renderApp('/reservations')
    await findScreenHeading('My hires')
    queryClient.setQueryData(PRIVATE_KEY, [{ reference: 'TSH-R-26-000123' }])

    await user.click(screen.getByRole('button', { name: SIGN_OUT }))

    expect(await findScreenHeading(CATALOGUE_HEADING)).toBeVisible()
    expect(currentAddress()).toBe('/')
    expect(await screen.findByRole('link', { name: 'Sign in' })).toBeVisible()
    expect(network.requestsTo(LOGOUT_ROUTE)).toHaveLength(1)
    await waitFor(() => expect(queryClient.getQueryData(PRIVATE_KEY)).toBeUndefined())
    // The token is gone. The next protected request carries none.
    await act(async () => {
      await getCurrentUser().catch(() => undefined)
    })
    const calls = network.requestsTo(ME_ROUTE)
    expect(bearerOf(calls[calls.length - 1])).toBeNull()
  })

  it('never passes through the sign in screen on the way out', async () => {
    const user = userEvent.setup()
    const network = mockApi({
      ...signedInAs(CUSTOMER),
      // The server takes its time, so there is a moment to look at.
      [LOGOUT_ROUTE]: () => new Promise<Response>((resolve) => setTimeout(() => resolve(noContentResponse()), 30)),
    })
    renderApp('/account')
    await findScreenHeading('My account')

    await user.click(screen.getByRole('button', { name: SIGN_OUT }))

    await findScreenHeading(CATALOGUE_HEADING)
    await waitFor(() => expect(network.requestsTo(LOGOUT_ROUTE)).toHaveLength(1))
    expect(screen.queryByRole('heading', { name: SIGN_IN_HEADING })).not.toBeInTheDocument()
    await screen.findByRole('link', { name: 'Sign in' })
    expect(currentAddress()).toBe('/')
  })
})

describe('a session that ends underneath a person', () => {
  it('sends them from a protected screen to sign in, with a message and the way back', async () => {
    const network = mockApi(sessionThatEnds())
    const { queryClient } = renderApp('/reservations')
    await findScreenHeading('My hires')
    queryClient.setQueryData(PRIVATE_KEY, [{ reference: 'TSH-R-26-000123' }])

    // A request on that screen finds the token no longer works.
    await act(async () => {
      await getCurrentUser().catch(() => undefined)
    })

    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
    expect(currentAddress()).toBe('/signin?next=%2Freservations')
    expect(screen.getByText('Your session has ended')).toBeVisible()
    expect(screen.getByText(/take you back to where you were/)).toBeVisible()
    expect(network.requestsTo(REFRESH_ROUTE)).toHaveLength(2)
    expect(queryClient.getQueryData(PRIVATE_KEY)).toBeUndefined()
  })

  it('sends them from a public screen to sign in too, and brings them back after', async () => {
    const user = userEvent.setup()
    const routes = sessionThatEnds()
    const network = mockApi(routes)

    // The connectivity screen is public, and it calls the protected endpoint
    // as soon as somebody is signed in.
    renderApp('/system')

    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
    expect(currentAddress()).toBe('/signin?next=%2Fsystem')
    expect(screen.getByText('Your session has ended')).toBeVisible()

    network.setRoute(LOGIN_ROUTE, () => jsonResponse(grantFor(CUSTOMER)))
    network.setRoute(ME_ROUTE, () => jsonResponse(CUSTOMER))
    await user.type(screen.getByLabelText('Email address'), CUSTOMER.email)
    await user.type(screen.getByLabelText('Password'), 'a-password-typed-by-a-person')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await findScreenHeading('System connectivity')).toBeVisible()
    expect(currentAddress()).toBe('/system')
    expect(await screen.findByText('The protected endpoint answered')).toBeVisible()
    const calls = network.requestsTo(ME_ROUTE)
    expect(bearerOf(calls[calls.length - 1])).toBe(ACCESS_TOKEN)
  })
})
