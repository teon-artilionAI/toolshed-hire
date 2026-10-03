/**
 * Tests for the shell around every screen.
 *
 * The layout and the menu follow whoever is signed in, and the notice about
 * sample data follows the `live` flag of the screen. I open the whole
 * application as each kind of person and read the navigation the way a person
 * or a screen reader would.
 */

import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NO_ACCESS_HEADING } from './no-access'
import { SAMPLE_DATA_TITLE } from './sample-data-notice'
import { mockApi, problemResponse } from '../test/api-mock'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../test/render-app'
import {
  ADMIN,
  BRANCHES_ROUTE,
  COUNTER_STAFF,
  CUSTOMER,
  SIGNED_OUT,
  signedInAs,
} from '../test/session-samples'

/** The customer header writes the label twice, once for each screen width,
 *  and a stylesheet hides one of them. A test has no stylesheet, so it sees
 *  both, and the name is matched loosely. */
const SIGN_OUT = /Sign out/

/** The labels in the menus a wide screen shows. A phone shows the same items
 *  again in its tab bar, and a set drops that repeat. */
function menuLabels(): Set<string> {
  const labels = screen
    .getAllByRole('navigation', { name: 'Primary' })
    .flatMap((navigation) => within(navigation).queryAllByRole('link'))
    .map((link) => link.textContent ?? '')
  return new Set(labels)
}

const CUSTOMER_MENU = new Set(['Catalogue', 'Search', 'Basket', 'My Hires', 'Account'])
const COUNTER_MENU = ['Today', 'Diary', 'Customers', 'New Booking', 'Locator', 'Overdue']
const ADMIN_MENU = ['Overview', 'Catalogue', 'Assets', 'Reports', 'Users', 'Audit']

describe('the menu and the layout', () => {
  it('offers a visitor the customer menu and a way to sign in', async () => {
    mockApi(SIGNED_OUT)

    renderApp('/basket')
    await findScreenHeading('Your hire basket')

    expect(menuLabels()).toEqual(CUSTOMER_MENU)
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/signin')
    expect(screen.queryByRole('button', { name: SIGN_OUT })).not.toBeInTheDocument()
  })

  it('offers a customer the customer menu and a way to sign out', async () => {
    mockApi(signedInAs(CUSTOMER))

    renderApp('/reservations')
    await findScreenHeading('My hires')

    expect(menuLabels()).toEqual(CUSTOMER_MENU)
    expect(screen.getByRole('button', { name: SIGN_OUT })).toBeEnabled()
    expect(screen.queryByRole('link', { name: 'Sign in' })).not.toBeInTheDocument()
  })

  it('offers counter staff the counter menu, under the name of their branch', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/counter')
    await findScreenHeading('Today at the counter')

    expect(menuLabels()).toEqual(new Set(COUNTER_MENU))
    // The account says BLV. The name comes from the API.
    expect((await screen.findAllByText('Bellville', {}, SCREEN_WAIT)).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Stikland branch counter').length).toBeGreaterThan(0)
    expect(screen.getAllByText(COUNTER_STAFF.fullName).length).toBeGreaterThan(0)
  })

  it('shows the branch code when the branch names cannot be loaded', async () => {
    mockApi({ ...signedInAs(COUNTER_STAFF), [BRANCHES_ROUTE]: () => problemResponse(500) })

    renderApp('/counter')
    await findScreenHeading('Today at the counter')

    expect((await screen.findAllByText('Branch BLV', {}, SCREEN_WAIT)).length).toBeGreaterThan(0)
  })

  it('offers an admin the admin menu and the counter menu', async () => {
    mockApi(signedInAs(ADMIN))

    renderApp('/admin')
    await findScreenHeading('Business overview')

    expect(menuLabels()).toEqual(new Set([...ADMIN_MENU, ...COUNTER_MENU]))
    expect(screen.getAllByText('Owner and admin').length).toBeGreaterThan(0)
  })

  it('keeps the staff layout when staff open a public screen', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/basket')
    await findScreenHeading('Your hire basket')

    expect(menuLabels()).toEqual(new Set(COUNTER_MENU))
  })

  it('has no demonstration control for switching role', async () => {
    mockApi(signedInAs(ADMIN))

    renderApp('/admin')
    await findScreenHeading('Business overview')

    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: /demonstration/i })).not.toBeInTheDocument()
  })
})

describe('the current page in the menu', () => {
  /** Every link with this name in the menus, the wide one and the phone one. */
  function menuLinks(name: string): HTMLElement[] {
    const links = screen
      .getAllByRole('navigation', { name: 'Primary' })
      .flatMap((navigation) => within(navigation).queryAllByRole('link', { name }))
    expect(links.length).toBeGreaterThan(0)
    return links
  }

  function expectCurrent(name: string, current: boolean): void {
    for (const link of menuLinks(name)) {
      if (current) expect(link).toHaveAttribute('aria-current', 'page')
      else expect(link).not.toHaveAttribute('aria-current')
    }
  }

  it('marks Today only on the counter home, although every counter address starts with it', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/counter/diary')
    await findScreenHeading('Branch diary')

    expectCurrent('Diary', true)
    expectCurrent('Today', false)
  })

  it('marks Today on the counter home itself', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/counter')
    await findScreenHeading('Today at the counter')

    expectCurrent('Today', true)
    expectCurrent('Diary', false)
  })

  it('marks the admin Overview only on its own address', async () => {
    mockApi(signedInAs(ADMIN))

    renderApp('/admin/users')
    await screen.findAllByRole('link', { name: 'Users' }, SCREEN_WAIT)

    expectCurrent('Users', true)
    expectCurrent('Overview', false)
  })

  it('still marks My Hires on the detail of one hire, which is not a home', async () => {
    mockApi(signedInAs(CUSTOMER))

    renderApp('/reservations/TSH-R-26-000124')
    await findScreenHeading('Booking detail')

    expectCurrent('My Hires', true)
    expectCurrent('Catalogue', false)
  })
})

describe('the sample data notice in the shell', () => {
  it('is above a screen that is not connected yet', async () => {
    mockApi(signedInAs(COUNTER_STAFF))

    renderApp('/counter/damage/TSH-DR-0042')
    const title = await findScreenHeading('Record damage')

    const notice = screen.getByText(SAMPLE_DATA_TITLE)
    expect(notice).toBeVisible()
    // Above the screen in the document, so it is read first and covers nothing.
    expect(notice.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(screen.getByRole('main')).getByText(SAMPLE_DATA_TITLE)).toBe(notice)
  })

  it.each([
    ['/signin', 'Sign in to Toolshed Hire'],
    ['/basket', 'Your hire basket'],
    ['/register', 'Create your hire account'],
    ['/privacy', 'Privacy notice'],
  ])('is not on %s, a public screen that is connected', async (opened, heading) => {
    mockApi(SIGNED_OUT)

    renderApp(opened)
    await findScreenHeading(heading)

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })

  it.each([
    ['/reservations', 'My hires'],
    ['/reservations/TSH-R-26-000124', 'Booking detail'],
    ['/account', 'My account'],
  ])('is not on %s, a protected screen that reads from the API', async (opened, heading) => {
    mockApi(signedInAs(CUSTOMER))

    renderApp(opened)
    await findScreenHeading(heading)

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })

  it('is not above a refusal, because no sample data is shown there', async () => {
    mockApi(signedInAs(CUSTOMER))

    renderApp('/counter')
    await findScreenHeading(NO_ACCESS_HEADING)

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
  })
})
