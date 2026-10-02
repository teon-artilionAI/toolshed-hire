/**
 * Tests for the privacy notice and the way to it.
 *
 * The page is public and holds words only. The shell links to it from the
 * footer of every screen, in all three layouts, and the registration form
 * links to it beside its acceptance box, which SC05-Register.test.tsx covers.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { SCREENS, screensForRole } from '../../shared/navigation'
import { accessTo } from '../../shared/screen-access'
import { mockApi } from '../../test/api-mock'
import { currentAddress, findScreenHeading, renderApp } from '../../test/render-app'
import { ADMIN, COUNTER_STAFF, CUSTOMER, SIGNED_OUT, signedInAs } from '../../test/session-samples'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'

const HEADING = 'Privacy notice'

/** The number of screens the documented inventory has. */
const NUMBERED_SCREENS = 24

function footerLink(): HTMLElement {
  return within(screen.getByRole('contentinfo')).getByRole('link', { name: 'Privacy notice' })
}

describe('the privacy notice', () => {
  it('opens for a visitor who has not signed in, and asks nothing of the API', async () => {
    const network = mockApi(SIGNED_OUT)

    renderApp('/privacy')

    expect(await findScreenHeading(HEADING)).toBeVisible()
    expect(currentAddress()).toBe('/privacy')
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(network.requests.filter((request) => request.path !== '/api/auth/refresh')).toEqual([])
  })

  it('says who is responsible and that nobody should enter real information', async () => {
    mockApi(SIGNED_OUT)
    renderApp('/privacy')
    await findScreenHeading(HEADING)

    const main = within(screen.getByRole('main'))
    expect(main.getByText('Do not enter real personal information')).toBeVisible()
    expect(main.getAllByText(/fictional .*built\s+as a university project/).length).toBeGreaterThan(0)
  })

  it('has a section for each thing a person needs to know', async () => {
    mockApi(SIGNED_OUT)
    renderApp('/privacy')
    await findScreenHeading(HEADING)

    const sections = screen.getAllByRole('heading', { level: 2 }).map((heading) => heading.textContent)
    expect(sections).toEqual([
      'Who is responsible',
      'What we collect and why',
      'What we never collect',
      'Who handles it and where',
      'Marketing',
      'How long we keep it',
      'Your rights',
      'If you want to complain',
    ])
  })

  it('says what is collected, what never is, where it is held and who to complain to', async () => {
    mockApi(SIGNED_OUT)
    renderApp('/privacy')
    await findScreenHeading(HEADING)

    const page = screen.getByRole('main')
    expect(page).toHaveTextContent(/last four characters of its number/)
    expect(page).toHaveTextContent(/hire and charge history/)
    expect(page).toHaveTextContent(/full identity number, passport number or licence number/)
    expect(page).toHaveTextContent(/Card details or bank details/)
    expect(page).toHaveTextContent(/database is held by Neon in London/)
    expect(page).toHaveTextContent(/runs on Google Cloud in London/)
    expect(page).toHaveTextContent(/served by Vercel/)
    expect(page).toHaveTextContent(/sent through Resend/)
    expect(page).toHaveTextContent(/Nothing you give us is used for marketing/)
    expect(page).toHaveTextContent(/not fixed yet\. It will be stated here before this system is used for real customers/)
    expect(page).toHaveTextContent(/ask to see the information we hold about you, ask us to correct it, and object/)
    expect(page).toHaveTextContent(/Information Regulator of South Africa/)
  })
})

describe('the privacy notice in the screen inventory', () => {
  it('is public, routed from the table, and outside the numbered screens', () => {
    const notice = SCREENS.find((candidate) => candidate.path === '/privacy')

    expect(notice).toMatchObject({ id: 'INFO-01', publicAccess: true, live: true, supporting: true })
    expect(notice?.inNav).toBeUndefined()
    if (notice) expect(accessTo(notice, null)).toBe('allowed')
  })

  it('leaves the count of numbered screens at twenty four', () => {
    const numbered = [...screensForRole('customer'), ...screensForRole('counter'), ...screensForRole('admin')]

    expect(numbered).toHaveLength(NUMBERED_SCREENS)
    expect(numbered.every((candidate) => candidate.id.startsWith('SC-'))).toBe(true)
    expect(SCREENS.filter((candidate) => candidate.id.startsWith('SC-'))).toHaveLength(NUMBERED_SCREENS)
  })
})

describe('the footer of every screen', () => {
  it.each([
    ['a visitor on the catalogue basket', SIGNED_OUT, '/basket', 'Your hire basket'],
    ['a visitor on sign in', SIGNED_OUT, '/signin', 'Sign in to Toolshed Hire'],
    ['a customer on My Hires', signedInAs(CUSTOMER), '/reservations', 'My hires'],
    ['counter staff on the counter', signedInAs(COUNTER_STAFF), '/counter', 'Today at the counter'],
    ['an admin on the overview', signedInAs(ADMIN), '/admin', 'Business overview'],
    ['a visitor on a page that does not exist', SIGNED_OUT, '/nowhere', 'We cannot find that page'],
    ['a customer refused the counter', signedInAs(CUSTOMER), '/counter', 'You do not have access to this screen'],
  ])('links to the privacy notice for %s', async (_who, session, opened, heading) => {
    mockApi(session)

    renderApp(opened)
    await findScreenHeading(heading)

    expect(footerLink()).toHaveAttribute('href', '/privacy')
  })

  it('takes a person to the notice, and focus goes with them', async () => {
    mockApi(SIGNED_OUT)
    renderApp('/basket')
    await findScreenHeading('Your hire basket')

    await userEvent.setup().click(footerLink())

    expect(await findScreenHeading(HEADING)).toBeVisible()
    expect(currentAddress()).toBe('/privacy')
    expect(screen.getByRole('main')).toHaveFocus()
  })
})
