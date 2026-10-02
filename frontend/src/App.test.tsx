/**
 * Tests for the guard on every route.
 *
 * Each test opens the whole application on one address as one kind of person
 * and looks at what they are shown. Signed out, signed in with a role that
 * does not reach the screen, and signed in with one that does.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { NO_ACCESS_HEADING } from './shared/no-access'
import { SAMPLE_DATA_TITLE } from './shared/sample-data-notice'
import { jsonResponse, mockApi } from './test/api-mock'
import { SCREEN_WAIT, currentAddress, findScreenHeading, renderApp } from './test/render-app'
import {
  ADMIN,
  COUNTER_STAFF,
  CUSTOMER,
  LOGIN_ROUTE,
  SIGNED_OUT,
  STILL_CHECKING,
  grantFor,
  signedInAs,
} from './test/session-samples'

const SIGN_IN_HEADING = 'Sign in to Toolshed Hire'
const COUNTER_HEADING = 'Today at the counter'
const ADMIN_HEADING = 'Business overview'
const MY_HIRES_HEADING = 'My hires'

describe('before the session is known', () => {
  it('shows a neutral loading state, and neither the screen nor a redirect', async () => {
    mockApi(STILL_CHECKING)

    renderApp('/counter')

    expect(await screen.findByText('Loading Toolshed Hire')).toBeVisible()
    expect(currentAddress()).toBe('/counter')
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })
})

describe('a signed out person', () => {
  it.each([
    ['/reservations', '/signin?next=%2Freservations'],
    ['/account', '/signin?next=%2Faccount'],
    ['/counter', '/signin?next=%2Fcounter'],
    ['/counter/checkout/rn-1', '/signin?next=%2Fcounter%2Fcheckout%2Frn-1'],
    ['/admin/users', '/signin?next=%2Fadmin%2Fusers'],
  ])('who opens %s is sent to sign in, with the way back kept', async (opened, landed) => {
    mockApi(SIGNED_OUT)

    renderApp(opened)

    expect(await findScreenHeading(SIGN_IN_HEADING)).toBeVisible()
    expect(currentAddress()).toBe(landed)
    expect(screen.getByText('Sign in to carry on')).toBeVisible()
  })

  it('is brought back to the screen they wanted once they have signed in', async () => {
    const user = userEvent.setup()
    mockApi({
      ...signedInAs(COUNTER_STAFF),
      ...SIGNED_OUT,
      [LOGIN_ROUTE]: () => jsonResponse(grantFor(COUNTER_STAFF)),
    })
    renderApp('/counter/diary')
    await findScreenHeading(SIGN_IN_HEADING)

    await user.type(screen.getByLabelText('Email address'), COUNTER_STAFF.email)
    await user.type(screen.getByLabelText('Password'), 'a-password-typed-by-a-person')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await findScreenHeading('Branch diary')).toBeVisible()
    expect(currentAddress()).toBe('/counter/diary')
  })

  it('may open a public screen without being asked to sign in', async () => {
    mockApi(SIGNED_OUT)

    renderApp('/basket')

    expect(await findScreenHeading('Your hire basket')).toBeVisible()
    expect(currentAddress()).toBe('/basket')
  })
})

describe('a signed in person whose role does not reach the screen', () => {
  it.each([
    ['a customer', '/counter', CUSTOMER, COUNTER_HEADING, '/'],
    ['a customer', '/admin', CUSTOMER, ADMIN_HEADING, '/'],
    ['counter staff', '/admin', COUNTER_STAFF, ADMIN_HEADING, '/counter'],
    ['counter staff', '/reservations', COUNTER_STAFF, MY_HIRES_HEADING, '/counter'],
    ['an admin', '/reservations', ADMIN, MY_HIRES_HEADING, '/admin'],
  ])('is told so and offered their own home, %s at %s', async (_who, opened, account, refused, home) => {
    mockApi(signedInAs(account))

    renderApp(opened)

    expect(await findScreenHeading(NO_ACCESS_HEADING)).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent(account.fullName)
    expect(screen.getByRole('link', { name: 'Go to my home screen' })).toHaveAttribute('href', home)
    // The address is left alone, and the screen itself is never drawn.
    expect(currentAddress()).toBe(opened)
    expect(screen.queryByRole('heading', { name: refused })).not.toBeInTheDocument()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    await waitFor(() => expect(document.title).toBe('No access | Toolshed Hire'))
  })
})

describe('a signed in person whose role reaches the screen', () => {
  it.each([
    ['a customer', '/reservations', CUSTOMER, MY_HIRES_HEADING],
    ['counter staff', '/counter', COUNTER_STAFF, COUNTER_HEADING],
    ['an admin', '/admin', ADMIN, ADMIN_HEADING],
    ['an admin', '/counter', ADMIN, COUNTER_HEADING],
  ])('sees it, %s at %s', async (_who, opened, account, heading) => {
    mockApi(signedInAs(account))

    renderApp(opened)

    expect(await findScreenHeading(heading)).toBeVisible()
    expect(currentAddress()).toBe(opened)
    expect(screen.queryByText(NO_ACCESS_HEADING)).not.toBeInTheDocument()
  })

  it('still reaches every public screen', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/basket')

    expect(await findScreenHeading('Your hire basket')).toBeVisible()
  })
})

describe('an address no screen has', () => {
  it('says so and offers the catalogue to a visitor', async () => {
    mockApi(SIGNED_OUT)

    renderApp('/nowhere')

    expect(await findScreenHeading('We cannot find that page')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Take me home' })).toHaveAttribute('href', '/')
  })

  it('offers a signed in person the home of their role', async () => {
    mockApi(signedInAs(ADMIN))

    renderApp('/nowhere')

    await screen.findByRole('link', { name: 'Take me home' }, SCREEN_WAIT)
    expect(screen.getByRole('link', { name: 'Take me home' })).toHaveAttribute('href', '/admin')
  })
})
